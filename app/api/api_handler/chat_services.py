import asyncio
import re
import threading
from time import perf_counter
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.search_engine import hybrid_search
from app.core.chat_handler import handle_chat
from app.api.model.chat_models import ChatRequest, ErrorResponse
from config.config import Config

# Bộ nhớ lưu các Session đang xử lý (Khóa Session chống Spam)
PROCESSING_SESSIONS = set()
_PROCESSING_LOCK = threading.Lock()
# ponytail: per-process limit; use shared admission control if Uvicorn gains workers.
_MODEL_REQUEST_SLOTS = asyncio.Semaphore(Config.MAX_PARALLEL_REQUESTS)


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
    session_key = f"{user_uid}:{session_id}"
    with _PROCESSING_LOCK:
        if session_key in PROCESSING_SESSIONS:
            return None, _lock_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Bot đang xử lý câu hỏi trước trong phiên này, vui lòng đợi chút nhé!",
                "SESSION_LOCKED",
            )

        PROCESSING_SESSIONS.add(session_key)
        return session_key, None


def _release_processing_slot(session_key: str | None) -> None:
    if session_key is None:
        return

    with _PROCESSING_LOCK:
        PROCESSING_SESSIONS.discard(session_key)

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
    started = perf_counter()

    try:
        try:
            await asyncio.wait_for(
                _MODEL_REQUEST_SLOTS.acquire(),
                timeout=Config.MODEL_QUEUE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return _lock_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Bot đang có nhiều yêu cầu. Vui lòng thử lại sau {Config.MODEL_QUEUE_TIMEOUT_SECONDS:g} giây.",
                "MODEL_QUEUE_TIMEOUT",
            )

        try:
            try:
                # Timeout starts after this request reaches the front of the model queue. 
                result = await asyncio.wait_for(
                    handle_chat(
                        data.user_message,
                        kb,
                        vector_store,
                        user_uid=user_uid,
                        session_id=data.session_id,
                        build_df=build_df,
                    ),
                    timeout=Config.MODEL_PROCESSING_TIMEOUT_SECONDS
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
                raise
            except Exception as e:
                print(f"❌ [INTERNAL ERROR] {str(e)}")
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content=ErrorResponse(
                        error="Internal Server Error",
                        message="Đã xảy ra lỗi hệ thống. Vui lòng thử lại sau.",
                        code="INTERNAL_SERVER_ERROR"
                    ).model_dump()
                )
        finally:
            _MODEL_REQUEST_SLOTS.release()
    finally:
        print(f"[PERF] stage=request_total wall_ms={(perf_counter() - started) * 1000:.1f}")
        _release_processing_slot(session_key)
