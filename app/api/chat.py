# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Request, status, Depends, HTTPException
from app.utils.unit_converter import convert_unit
from app.memory.memory_store import clear_session, get_full_history_api
from app.guard.clarify import clear_session_context

# Import từ các module đã tách bạch
from app.api.model.chat_models import ChatRequest, EvalChatRequest, ChatResponse, ErrorResponse
from pydantic import BaseModel
from typing import Union, List

class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: str = "local"

from app.api.api_handler.chat_services import (
    process_chat_message,
    search_knowledge_base,
)
from app.api.auth.firebase_auth import verify_firebase_token
import os
from app.guard.security import limiter


RAG_MAGIC_KEY = "ragas_magic_key_2024"
router = APIRouter()

AUTH_RESPONSES = {
    401: {"description": "Firebase token không hợp lệ hoặc đã hết hạn"},
    403: {"description": "Thiếu Bearer token hoặc magic_key không hợp lệ"},
}

CHAT_ERROR_RESPONSES = {
    **AUTH_RESPONSES,
    400: {"model": ErrorResponse, "description": "Dữ liệu đầu vào không hợp lệ"},
    422: {"description": "Request validation error"},
    429: {"model": ErrorResponse, "description": "Too Many Requests - vượt giới hạn gọi API hoặc bot đang bận"},
    500: {"model": ErrorResponse, "description": "Lỗi hệ thống nội bộ (Internal Server Error)"},
    504: {"model": ErrorResponse, "description": "Hệ thống AI xử lý vượt quá thời gian quy định (Gateway Timeout)"},
}

@router.get(
    "/test-knowledge-base",
    tags=["Knowledge Base"],
    summary="Search the loaded knowledge base",
    responses={422: {"description": "Request validation error"}},
)
def test_kb(request: Request, q: str = None, category: str = None, top_k: int = 5):
    """API tìm kiếm lai (Hybrid Search)."""
    if getattr(request.app.state, "knowledge_base", None) is None:
        return {'status': 'Kho hàng trống!'}
    return search_knowledge_base(request, q, category, top_k)

@router.post(
    "/v1/embeddings",
    tags=["Knowledge Base"],
    summary="Create OpenAI-compatible embeddings",
    responses={422: {"description": "Request validation error"}, 500: {"description": "Embedding model not initialized"}},
)
def get_embeddings(request: Request, data: EmbeddingRequest):
    """
    OpenAI-compatible embeddings endpoint.
    Allows Ragas to use the Chatbot's loaded embedding model without duplicating it in VRAM.
    """
    if getattr(request.app.state, "vector_store", None) is None:
        raise HTTPException(status_code=500, detail="Embedding model not initialized.")
    
    embedder = request.app.state.vector_store.embeddings
    inputs = data.input if isinstance(data.input, list) else [data.input]
    
    embeddings = embedder.embed_documents(inputs)
    
    data_list = []
    for i, emb in enumerate(embeddings):
        data_list.append({
            "object": "embedding",
            "index": i,
            "embedding": emb
        })
        
    return {
        "object": "list",
        "data": data_list,
        "model": data.model,
        "usage": {"prompt_tokens": 0, "total_tokens": 0}
    }

@router.post(
    "/chat",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatResponse,
    responses=CHAT_ERROR_RESPONSES,
    summary="Gửi tin nhắn tới AI Chatbot",
    description="Xử lý câu hỏi của người dùng, kiểm tra tương thích linh kiện và trả về câu trả lời trọn vẹn theo chuẩn RESTful.",
    tags=["Chat"],
)
@limiter.limit("10/minute")
async def chat_with_bot(request: Request, data: ChatRequest, current_user: dict = Depends(verify_firebase_token)):
    user_uid = current_user["uid"]
    return await process_chat_message(request, data, user_uid, include_contexts=False)

@router.post(
    "/chat/eval",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatResponse,
    responses=CHAT_ERROR_RESPONSES,
    summary="Đánh giá RAG (Trả về cả Context thô)",
    description="Endpoint dành riêng cho Ragas evaluation, yêu cầu cung cấp magic_key.",
    tags=["Evaluation"],
)
@limiter.limit("40/minute")
async def chat_with_bot_eval(request: Request, data: EvalChatRequest, current_user: dict = Depends(verify_firebase_token)):
    if data.magic_key != RAG_MAGIC_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid Magic Key"
        )
    user_uid = current_user["uid"]
    return await process_chat_message(request, data, user_uid, include_contexts=True)

# @router.get(
#     "/calculate",
#     tags=["Tools"],
#     summary="Convert hardware units",
# )
# def calculate(value: float, from_unit: str, to_unit: str):
#     """Unit conversion calculator API.

#     Examples:
#         /calculate?value=64&from_unit=GB&to_unit=MB
#         /calculate?value=3.5&from_unit=GHz&to_unit=MHz
#     """
#     try:
#         result = convert_unit(value, from_unit, to_unit)
#         return {"status": "success", "result": result}
#     except ValueError as e:
#         return {"status": "error", "message": str(e)}

@router.delete("/sessions/{session_id}", tags=["Sessions"], summary="Delete chat session history", responses={**AUTH_RESPONSES, 422: {"description": "Request validation error"}})
@router.delete("/chat/history/{session_id}", tags=["Sessions"], include_in_schema=False)
def delete_history(session_id: str, current_user: dict = Depends(verify_firebase_token)):
    """Xóa lịch sử hội thoại của một user."""
    user_uid = current_user["uid"]
    clear_session(user_uid, session_id)
    clear_session_context(session_id)
    return {"status": "ok", "message": f"Đã xóa lịch sử session '{session_id}'"}


