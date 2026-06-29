import asyncio
import re
import threading
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.search_engine import hybrid_search
from app.core.chat_handler import handle_chat
from app.api.model.chat_models import ChatRequest, ErrorResponse

_stop_events: dict[str, threading.Event] = {}

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

def register_stop_event(session_id: str) -> threading.Event:
    """Tạo và đăng ký stop event cho một session."""
    stop_event = threading.Event()
    _stop_events[session_id] = stop_event
    return stop_event

def trigger_stop_event(session_id: str) -> bool:
    """Kích hoạt cờ dừng cho session nếu đang chạy."""
    if session_id in _stop_events:
        _stop_events[session_id].set()
        return True
    return False

async def process_chat_message(request: Request, data: ChatRequest):
    """Xử lý toàn bộ logic nghiệp vụ cho Chat API (Validate, chạy LLM, xử lý Timeout 30s)."""
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
                session_id=data.session_id,
                build_df=build_df,
            ),
            timeout=30.0
        )
        return result
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=ErrorResponse(
                error="Timeout Error",
                message="Hệ thống AI xử lý quá lâu. Vui lòng thử lại sau.",
                code="LLM_GENERATION_TIMEOUT"
            ).model_dump()
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="Internal Server Error",
                message=f"Lỗi hệ thống: {str(e)}",
                code="INTERNAL_SERVER_ERROR"
            ).model_dump()
        )
