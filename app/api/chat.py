import re
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.chat_handler import handle_chat
from app.core.search_engine import hybrid_search
from app.utils.unit_converter import convert_unit
from app.memory.memory_store import clear_session

router = APIRouter()

def _validate_session_id(session_id: str) -> bool:
    """Chỉ cho phép chữ, số, gạch ngang/dưới, tối đa 64 ký tự."""
    return bool(re.match(r'^[a-zA-Z0-9_\-]{1,64}$', session_id))

def _search(request: Request, q: str = None, category: str = None, top_k: int = 5):
    """Thin wrapper around ``hybrid_search`` that injects the global state."""
    # Lấy state từ request.app.state
    kb = getattr(request.app.state, "knowledge_base", None)
    model = getattr(request.app.state, "embedding_model", None)
    corpus = getattr(request.app.state, "corpus_embeddings", None)
    
    if kb is None or model is None or corpus is None:
        return []

    return hybrid_search(q, category, top_k, kb, model, corpus)

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

    # Định nghĩa hàm search_fn động truyền vào chat_handler
    search_fn = lambda q=None, category=None, top_k=5: _search(request, q, category, top_k)

    kb = getattr(request.app.state, "knowledge_base", None)
    compat_rules = getattr(request.app.state, "compatibility_rules", None)
    build_df = getattr(request.app.state, "build_data", None)

    return handle_chat(
        data.user_message,
        kb,
        compat_rules,
        search_fn,
        session_id=data.session_id,
        build_df=build_df,
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
def delete_history(session_id: str):
    """Xóa lịch sử hội thoại của một user."""
    clear_session(session_id)
    return {"status": "ok", "message": f"Đã xóa lịch sử session '{session_id}'"}
