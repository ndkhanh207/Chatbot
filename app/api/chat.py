import re
import threading
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.chat_handler import handle_chat, handle_chat_stream
from app.core.search_engine import hybrid_search
from app.utils.unit_converter import convert_unit
from app.memory.memory_store import clear_session

router = APIRouter()
_stop_events: dict[str, threading.Event] = {}

def _validate_session_id(session_id: str) -> bool:
    """Chỉ cho phép chữ, số, gạch ngang/dưới, tối đa 64 ký tự."""
    return bool(re.match(r'^[a-zA-Z0-9_\-]{1,64}$', session_id))

def _search(request: Request, q: str = None, category: str = None, top_k: int = 5):
    """Thin wrapper around ``hybrid_search`` that injects the global state."""
    # Lấy state từ request.app.state
    kb = getattr(request.app.state, "knowledge_base", None)
    vector_store = getattr(request.app.state, "vector_store", None)
    
    if kb is None or vector_store is None:
        return []

    return hybrid_search(q, category, top_k, kb, vector_store)

@router.get('/test-knowledge-base')
def test_kb(request: Request, q: str = None, category: str = None, top_k: int = 5):
    """API tìm kiếm lai (Hybrid Search)."""
    if getattr(request.app.state, "knowledge_base", None) is None:
        return {'status': 'Kho hàng trống!'}
    return _search(request, q, category, top_k)

class ChatRequest(BaseModel):
    user_message: str
    session_id: str = "default"

@router.post("/chat")
def chat_with_bot(request: Request, data: ChatRequest):
    """API chatbot hoàn chỉnh với tính năng kiểm tra tương thích và gợi ý bộ PC."""
    if not _validate_session_id(data.session_id):
        return {"chatbot_reply": "Session ID không hợp lệ. Chỉ dùng chữ, số, '-', '_' (tối đa 64 ký tự)."}

    kb = getattr(request.app.state, "knowledge_base", None)
    vector_store = getattr(request.app.state, "vector_store", None)
    build_df = getattr(request.app.state, "build_data", None)

    return handle_chat(
        data.user_message,
        kb,
        vector_store,
        session_id=data.session_id,
        build_df=build_df,
    )

@router.post("/chat/{session_id}/stop")
def stop_chat_generation(session_id: str):
    """Nhận tín hiệu từ UI để bật cờ dừng (Cooperative Cancellation) cho session tương ứng."""
    if session_id in _stop_events:
        _stop_events[session_id].set()
        return {"status": "success", "message": f"Đã gửi tín hiệu dừng cho session '{session_id}'"}
    return {"status": "not_found", "message": f"Session '{session_id}' không chạy hoặc đã kết thúc"}

@router.post("/chat/stream")
def chat_stream_endpoint(request: Request, data: ChatRequest):
    """API chatbot hỗ trợ sinh token trực tiếp (Streaming) kết hợp cờ ngắt hợp tác."""
    if not _validate_session_id(data.session_id):
        return {"chatbot_reply": "Session ID không hợp lệ. Chỉ dùng chữ, số, '-', '_' (tối đa 64 ký tự)."}

    kb = getattr(request.app.state, "knowledge_base", None)
    vector_store = getattr(request.app.state, "vector_store", None)
    build_df = getattr(request.app.state, "build_data", None)

    stop_event = threading.Event()
    _stop_events[data.session_id] = stop_event

    return StreamingResponse(
        handle_chat_stream(
            data.user_message,
            kb,
            vector_store,
            session_id=data.session_id,
            build_df=build_df,
            stop_event=stop_event,
        ),
        media_type="text/event-stream"
    )

@router.get("/calculate")
def calculate(value: float, from_unit: str, to_unit: str):
    """Unit conversion calculator API.

    Examples:
        /calculate?value=64&from_unit=GB&to_unit=MB
        /calculate?value=3.5&from_unit=GHz&to_unit=MHz
    """
    try:
        result = convert_unit(value, from_unit, to_unit)
        return {"status": "success", "result": result}
    except ValueError as e:
        return {"status": "error", "message": str(e)}

@router.delete("/sessions/{session_id}")
@router.delete("/chat/history/{session_id}")
def delete_history(session_id: str):
    """Xóa lịch sử hội thoại của một user."""
    clear_session(session_id)
    return {"status": "ok", "message": f"Đã xóa lịch sử session '{session_id}'"}
