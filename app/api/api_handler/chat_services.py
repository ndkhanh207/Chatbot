import asyncio
import re
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.search_engine import hybrid_search
from app.core.chat_handler import handle_chat
from app.api.model.chat_models import ChatRequest, ErrorResponse

# Bộ nhớ lưu các Session đang xử lý (Khóa Session chống Spam)
PROCESSING_SESSIONS = set()

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

async def process_chat_message(request: Request, data: ChatRequest, user_uid: str):
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

    # 1. KIỂM TRA KHÓA SESSION (Chống Spam / Nhồi Request)
    if data.session_id in PROCESSING_SESSIONS:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=ErrorResponse(
                error="Too Many Requests",
                message="Bot đang suy nghĩ câu hỏi trước của bạn, vui lòng đợi chút nhé!",
                code="SESSION_LOCKED"
            ).model_dump()
        )

    # Khóa session này lại
    PROCESSING_SESSIONS.add(data.session_id)

    kb = getattr(request.app.state, "knowledge_base", None)

    vector_store = getattr(request.app.state, "vector_store", None)
    build_df = getattr(request.app.state, "build_data", None)

    try:
        # Chạy handle_chat (hàm đồng bộ) trong thread pool với timeout 30 giây
        result = await asyncio.wait_for(
            asyncio.to_thread(
                handle_chat,
                data.user_message,
                kb,
                vector_store,
                user_uid=user_uid,
                session_id=data.session_id,
                build_df=build_df,
            ),
            timeout=60.0  #   ép chết tác vụ nếu quá lâu
        )
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
        # Mở khóa session dù thành công hay thất bại
        PROCESSING_SESSIONS.discard(data.session_id)
