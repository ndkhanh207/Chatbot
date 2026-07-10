import asyncio
import re
import threading
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.search_engine import hybrid_search
from app.core.chat_handler import handle_chat
from app.api.model.chat_models import ChatRequest, ErrorResponse

# Bộ nhớ lưu các Session đang xử lý (Khóa Session chống Spam)
PROCESSING_SESSIONS = set()
_PROCESSING_LOCK = threading.Lock()
_ACTIVE_MODEL_REQUEST: str | None = None


def _lock_error(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error="Too Many Requests",
            message=message,
            code=code,
        ).model_dump()
    )


def _acquire_processing_slot(user_uid: str, session_id: str) -> tuple[str | None, JSONResponse | None]:
    global _ACTIVE_MODEL_REQUEST

    session_key = f"{user_uid}:{session_id}"
    with _PROCESSING_LOCK:
        if session_key in PROCESSING_SESSIONS:
            return None, _lock_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Bot đang xử lý câu hỏi trước trong phiên này, vui lòng đợi chút nhé!",
                "SESSION_LOCKED",
            )

        if _ACTIVE_MODEL_REQUEST is not None:
            return None, _lock_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Bot đang xử lý một câu hỏi khác, vui lòng gửi lại sau vài giây.",
                "MODEL_BUSY",
            )

        PROCESSING_SESSIONS.add(session_key)
        _ACTIVE_MODEL_REQUEST = session_key
        return session_key, None


def _release_processing_slot(session_key: str | None) -> None:
    global _ACTIVE_MODEL_REQUEST

    if session_key is None:
        return

    with _PROCESSING_LOCK:
        PROCESSING_SESSIONS.discard(session_key)
        if _ACTIVE_MODEL_REQUEST == session_key:
            _ACTIVE_MODEL_REQUEST = None

def validate_session_id(session_id: str) -> bool:
    """Chỉ cho phép chữ, số, gạch ngang/dưới, tối đa 64 ký tự."""
    return bool(re.match(r'^[a-zA-Z0-9_\-]{1,64}$', session_id))

def search_knowledge_base(request: Request, q: str = None, category: str = None, top_k: int = 5):
    """Thin wrapper around ``hybrid_search`` that injects the global state."""
    kb = getattr(request.app.state, "knowledge_base", None)
    vector_store = getattr(request.app.state, "vector_store", None)
    
    if kb is None or vector_store is None:
        return []

    return hybrid_search(q, category, top_k, kb, vector_store)

async def process_chat_message(request: Request, data: ChatRequest, user_uid: str, include_contexts: bool = False):
    """Xử lý toàn bộ logic nghiệp vụ cho Chat API (Validate, chạy LLM, xử lý Timeout 90s)."""
    if not data.user_message.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error="Validation Error",
                message="Nội dung tin nhắn không được để trống.",
                code="EMPTY_MESSAGE"
            ).model_dump()
        )

    if not validate_session_id(data.session_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error="Validation Error",
                message="Session không hợp lệ. Vui lòng thử lại ở phiên chat mới.",
                code="INVALID_SESSION_ID"
            ).model_dump()
        )

    session_key, lock_response = _acquire_processing_slot(user_uid, data.session_id)
    if lock_response is not None:
        return lock_response

    kb = getattr(request.app.state, "knowledge_base", None)

    vector_store = getattr(request.app.state, "vector_store", None)
    build_df = getattr(request.app.state, "build_data", None)

    try:
        # Chạy handle_chat (hàm async) trực tiếp với timeout 60 giây
        result = await asyncio.wait_for(
            handle_chat(
                data.user_message,
                kb,
                vector_store,
                user_uid=user_uid,
                session_id=data.session_id,
                build_df=build_df,
            ),
            timeout=60.0  #   ép chết tác vụ nếu quá lâu
        )

        if not include_contexts and "contexts" in result:
            del result["contexts"]

        return result
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=ErrorResponse(
                error="Timeout Error",
                message="Xin lỗi, câu hỏi này hơi phức tạp nên Bot suy nghĩ lâu quá. Bạn có thể hỏi lại ngắn gọn hơn được không?",
                code="LLM_GENERATION_TIMEOUT"
            ).model_dump()
        )
    except asyncio.CancelledError:
        print("⚠️ [REQUEST CANCELLED] Client ngắt kết nối. LLM Async Pipeline sẽ tự động đóng socket và giải phóng VRAM.")
        # Nếu muốn chắc chắn, có thể gọi torch.cuda.empty_cache() tại đây nhưng thường Ollama sẽ tự xử lý khi socket đóng
        raise
    except Exception as e:
        print(f"❌ [INTERNAL ERROR] {str(e)}") # Log lỗi chi tiết ở Backend
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="Internal Server Error",
                message="Đã xảy ra lỗi hệ thống. Vui lòng thử lại sau.", # Che giấu lỗi thật
                code="INTERNAL_SERVER_ERROR"
            ).model_dump()
        )
    finally:
        _release_processing_slot(session_key)
