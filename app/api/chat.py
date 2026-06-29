from fastapi import APIRouter, Request, status
from app.utils.unit_converter import convert_unit
from app.memory.memory_store import clear_session

# Import từ các module đã tách bạch
from app.api.model.chat_models import ChatRequest, ChatResponse, ErrorResponse
from app.api.api_handler.chat_services import (
    process_chat_message,
    search_knowledge_base,
)

router = APIRouter()

@router.get('/test-knowledge-base')
def test_kb(request: Request, q: str = None, category: str = None, top_k: int = 5):
    """API tìm kiếm lai (Hybrid Search)."""
    if getattr(request.app.state, "knowledge_base", None) is None:
        return {'status': 'Kho hàng trống!'}
    return search_knowledge_base(request, q, category, top_k)

@router.post(
    "/chat",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Dữ liệu đầu vào không hợp lệ (Tin nhắn rỗng hoặc Session ID sai định dạng)"},
        500: {"model": ErrorResponse, "description": "Lỗi hệ thống nội bộ (Internal Server Error)"},
        504: {"model": ErrorResponse, "description": "Hệ thống AI xử lý vượt quá thời gian quy định (Gateway Timeout)"},
    },
    summary="Gửi tin nhắn tới AI Chatbot (Non-streaming)",
    description="Xử lý câu hỏi của người dùng, kiểm tra tương thích linh kiện và trả về câu trả lời trọn vẹn theo chuẩn RESTful."
)
async def chat_with_bot(request: Request, data: ChatRequest):
    return await process_chat_message(request, data)

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
