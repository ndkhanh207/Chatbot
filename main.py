"""FastAPI application entry point."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config.config import EMBEDDING_MODEL as EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE, Config
from app.catalog import ChromaSemanticIndex, ShopCatalog, create_embeddings
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.guard.security import limiter

from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.model.chat_models import ErrorResponse

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "connect-src 'self';"
        )
        return response

from app.core.health import check_ollama_status, check_mysql_status, reset_ollama_model

# ──────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n=== [SYSTEM STARTUP] TRAM KIEM TRA HE THONG ===")

    # 1. Kiểm tra các dịch vụ cứng trước khi load dữ liệu nặng vào RAM
    ollama_ok = await check_ollama_status()
    mysql_ok = await check_mysql_status()

    if not ollama_ok or not mysql_ok:
        print("[CRITICAL] KHOI DONG THAT BAI: Mot so dich vu nen (Ollama/MySQL) chua san sang!")
        print("He thong se dung lai tai day de ban kiem tra docker/service.")
        raise RuntimeError("External services are offline.")

    print("--------------------------------------------------")
    print("=== [SYSTEM] Dich vu nen OK! Bat dau nap Knowledge Base... ===")

    try:
        semantic_index = None
        try:
            embeddings = create_embeddings()
            embeddings.embed_query("test")
            semantic_index = ChromaSemanticIndex(Config.VECTOR_DB_DIR, embeddings)
        except Exception as index_error:
            print(f"[CATALOG] Starting in keyword-only mode: {index_error}")

        app.state.catalog = ShopCatalog.load(
            Config.PC_STORE_DATA,
            semantic_index=semantic_index,
            embedding_config=(
                f"model={EMBEDDING_MODEL_NAME};device={EMBEDDING_DEVICE};"
                "batch=8;metric=cosine"
            ),
        )
        status = app.state.catalog.status()
        print(f"=== [CATALOG] {status.product_count} products | {status.build_count} builds | {status.mode} ===")
        print("=== [SYSTEM] Server initialization complete! Ready for API requests. ===\n")

    except Exception as e:
        print(f"❌ LỖI KHỞI TẠO HỆ THỐNG: {str(e)}")
        raise e

    try:
        yield
    finally:
        print("=== [SYSTEM] Shutting down Server... ===")
        try:
            if hasattr(app.state, "catalog"):
                del app.state.catalog
            
            # Ép Python dọn rác bộ nhớ
            import gc
            gc.collect()
            
            # Ép PyTorch giải phóng VRAM đã cấp phát nhưng không dùng
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                print("=== [SYSTEM] Đã dọn dẹp và giải phóng hoàn toàn VRAM (CUDA). ===")
        except Exception as e:
            print(f"⚠️ [SYSTEM] Lỗi khi dọn dẹp bộ nhớ: {e}")
            
        print("=== [SYSTEM] Unloading Ollama model... ===")
        await reset_ollama_model()

app = FastAPI(
    title="AI PC Builder Chatbot API",
    summary="Vietnamese RAG chatbot API for PC building, compatibility checks, pricing, and specs.",
    description=(
        "REST API for the AI PC Builder Chatbot. Use `/chat` for authenticated "
        "chat requests, `/chat/eval` for Ragas evaluation, and utility endpoints "
        "for health checks, embeddings, unit conversion, and knowledge-base search."
    ),
    version="1.0.0",
    lifespan=lifespan,
    contact={"name": "AI PC Builder Chatbot"},
    openapi_tags=[
        {"name": "Chat", "description": "Authenticated chatbot conversation endpoints."},
        {"name": "Evaluation", "description": "Ragas and internal evaluation endpoints."},
        {"name": "Knowledge Base", "description": "Direct search and embedding utilities."},
        {"name": "Tools", "description": "Small helper APIs used by the chatbot."},
        {"name": "Sessions", "description": "Chat history and session management."},
        {"name": "System", "description": "Health and operational status endpoints."},
    ],
    swagger_ui_parameters={
        "displayRequestDuration": True,
        "docExpansion": "none",
        "persistAuthorization": True,
        "tryItOutEnabled": True,
    },
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content=ErrorResponse(
            error="Too Many Requests",
            message="Rate limit exceeded. Please retry later.",
            code="RATE_LIMIT_EXCEEDED",
        ).model_dump(),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and {"error", "message", "code"} <= exc.detail.keys():
        content = ErrorResponse.model_validate(exc.detail).model_dump()
    else:
        defaults = {
            401: ("Authentication Error", "Authentication is required.", "AUTH_REQUIRED"),
            403: ("Forbidden", "Access is forbidden.", "FORBIDDEN"),
            404: ("Not Found", "Resource not found.", "NOT_FOUND"),
            405: ("Method Not Allowed", "HTTP method is not allowed.", "METHOD_NOT_ALLOWED"),
        }
        error, message, code = defaults.get(
            exc.status_code,
            ("HTTP Error", str(exc.detail), f"HTTP_{exc.status_code}"),
        )
        content = ErrorResponse(error=error, message=message, code=code).model_dump()
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    locations = {part for error in errors for part in error.get("loc", [])}
    if "session_id" in locations:
        message = "Session ID must use 1-64 letters, numbers, underscores, or hyphens."
        code = "INVALID_SESSION_ID"
    elif "user_message" in locations:
        message = "Message must contain 1-500 characters."
        code = "INVALID_MESSAGE"
    else:
        message = "Request data is invalid."
        code = "VALIDATION_ERROR"
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="Validation Error",
            message=message,
            code=code,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    print(f"❌ [UNHANDLED API ERROR] {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error",
            message="An unexpected server error occurred.",
            code="INTERNAL_SERVER_ERROR",
        ).model_dump(),
    )

app.add_middleware(SecurityHeadersMiddleware)

# Cấu hình CORS để cho phép frontend (Flutter/React/Postman) gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://customer-outskirts-blubber.ngrok-free.dev",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://10.0.2.2:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Cho phép tất cả các method (GET, POST, OPTIONS, DELETE,...)
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(health_router)
