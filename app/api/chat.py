import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.api_handler.chat_services import process_chat_message
from app.catalog import ProductQuery
from app.api.auth.firebase_auth import verify_firebase_token
from app.api.model.chat_models import (
    ChatRequest,
    ChatResponse,
    DeleteSessionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ErrorResponse,
    EvalChatRequest,
    EvalChatResponse,
    SessionId,
)
from app.guard.security import limiter
from app.memory.context_manager import ConversationContext
from config.config import Config


router = APIRouter()

AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Firebase token không hợp lệ hoặc đã hết hạn"},
    403: {"model": ErrorResponse, "description": "Không có quyền truy cập"},
}

CHAT_ERROR_RESPONSES = {
    **AUTH_RESPONSES,
    422: {"model": ErrorResponse, "description": "Request validation error"},
    429: {"model": ErrorResponse, "description": "Rate limit, session lock, or model queue timeout"},
    500: {"model": ErrorResponse, "description": "Internal server error"},
    503: {"model": ErrorResponse, "description": "Chat service unavailable"},
    504: {"model": ErrorResponse, "description": "LLM processing timeout"},
}


@router.get(
    "/test-knowledge-base",
    tags=["Knowledge Base"],
    summary="Search the loaded knowledge base",
    responses={422: {"model": ErrorResponse, "description": "Request validation error"}},
)
def test_kb(request: Request, q: str | None = None, category: str | None = None, top_k: int = 5):
    if getattr(request.app.state, "catalog", None) is None:
        return {"status": "Kho hàng trống!"}
    return [
        item.as_legacy_dict()
        for item in request.app.state.catalog.search_products(
            ProductQuery(text=q or "", category=category, limit=top_k)
        )
    ]


@router.post(
    "/v1/embeddings",
    response_model=EmbeddingResponse,
    tags=["Knowledge Base"],
    summary="Create OpenAI-compatible embeddings",
    responses={
        422: {"model": ErrorResponse, "description": "Request validation error"},
        503: {"model": ErrorResponse, "description": "Embedding model not initialized"},
    },
)
def get_embeddings(request: Request, data: EmbeddingRequest):
    if getattr(request.app.state, "catalog", None) is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ErrorResponse(
                error="Service Unavailable",
                message="Embedding model is not initialized.",
                code="EMBEDDING_NOT_READY",
            ).model_dump(),
        )

    inputs = data.input if isinstance(data.input, list) else [data.input]
    try:
        embeddings = request.app.state.catalog.embed_documents(inputs)
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ErrorResponse(
                error="Service Unavailable",
                message=str(error),
                code="EMBEDDING_NOT_READY",
            ).model_dump(),
        ) from error
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": embedding}
            for index, embedding in enumerate(embeddings)
        ],
        "model": data.model,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses=CHAT_ERROR_RESPONSES,
    summary="Gửi tin nhắn tới AI Chatbot",
    description="Xử lý câu hỏi và trả về câu trả lời cuối cùng.",
    tags=["Chat"],
)
@limiter.limit("10/minute")
async def chat_with_bot(
    request: Request,
    data: ChatRequest,
    current_user: dict = Depends(verify_firebase_token),
):
    return await process_chat_message(request, data, current_user["uid"], include_contexts=False)


@router.post(
    "/chat/eval",
    response_model=EvalChatResponse,
    responses=CHAT_ERROR_RESPONSES,
    summary="Đánh giá RAG",
    description="Trả về cả context thô; yêu cầu header X-Eval-Key.",
    tags=["Evaluation"],
)
@limiter.limit("40/minute")
async def chat_with_bot_eval(
    request: Request,
    data: EvalChatRequest,
    x_eval_key: Annotated[str | None, Header(alias="X-Eval-Key")] = None,
    current_user: dict = Depends(verify_firebase_token),
):
    if not Config.RAGAS_MAGIC_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ErrorResponse(
                error="Service Unavailable",
                message="Evaluation endpoint is not configured.",
                code="EVAL_NOT_CONFIGURED",
            ).model_dump(),
        )
    if x_eval_key is None or not secrets.compare_digest(x_eval_key, Config.RAGAS_MAGIC_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ErrorResponse(
                error="Forbidden",
                message="Invalid evaluation key.",
                code="INVALID_EVAL_KEY",
            ).model_dump(),
        )
    return await process_chat_message(request, data, current_user["uid"], include_contexts=True)


@router.delete(
    "/sessions/{session_id}",
    response_model=DeleteSessionResponse,
    tags=["Sessions"],
    summary="Delete chat session history",
    responses={**AUTH_RESPONSES, 422: {"model": ErrorResponse, "description": "Request validation error"}},
)

def delete_history(
    session_id: SessionId,
    current_user: dict = Depends(verify_firebase_token),
):
    user_uid = current_user["uid"]
    ConversationContext(user_uid, session_id).clear()
    return DeleteSessionResponse(message=f"Đã xóa lịch sử session '{session_id}'")
