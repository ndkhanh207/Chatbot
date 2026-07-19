import asyncio
import threading
from time import perf_counter
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.chat_handler import handle_chat
from app.api.model.chat_models import ChatRequest, ChatResponse, ErrorResponse, EvalChatResponse
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

async def process_chat_message(
    request: Request,
    data: ChatRequest,
    user_uid: str,
    include_contexts: bool = False,
) -> ChatResponse | EvalChatResponse | JSONResponse:
    """Run one chat request with per-session admission and bounded model execution."""
    catalog = getattr(request.app.state, "catalog", None)
    if catalog is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                error="Service Unavailable",
                message="Chat knowledge base is not ready.",
                code="CHAT_SERVICE_UNAVAILABLE",
            ).model_dump()
        )

    session_key, lock_response = _acquire_processing_slot(user_uid, data.session_id)
    if lock_response is not None:
        return lock_response

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
                        catalog,
                        user_uid=user_uid,
                        session_id=data.session_id,
                    ),
                    timeout=Config.MODEL_PROCESSING_TIMEOUT_SECONDS
                )

                if include_contexts:
                    return EvalChatResponse(
                        chatbot_reply=result["chatbot_reply"],
                        contexts=result.get("contexts", []),
                    )
                return ChatResponse(chatbot_reply=result["chatbot_reply"])
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
