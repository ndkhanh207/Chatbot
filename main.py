"""FastAPI application entry point."""

import asyncio
from pathlib import Path
import pandas as pd
import anyio
import ollama  # Import để check status
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config.config import EMBEDDING_MODEL as EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE, Config
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from app.core.data_loader import load_knowledge_base, initialize_vector_db
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.guard.security import limiter

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
            "img-src 'self' data: https://fastapi.tiangolo.com;"
        )
        return response

from app.core.health import check_ollama_status, check_mysql_status

# ──────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n=== 🚀 [SYSTEM STARTUP] TRẠM KIỂM TRA HỆ THỐNG ===")

    # 1. Kiểm tra các dịch vụ cứng trước khi load dữ liệu nặng vào RAM
    ollama_ok = await check_ollama_status()
    mysql_ok = await check_mysql_status()

    if not ollama_ok or not mysql_ok:
        print("❌ [CRITICAL] KHỞI ĐỘNG THẤT BẠI: Một số dịch vụ nền (Ollama/MySQL) chưa sẵn sàng!")
        print("⚠️ Hệ thống sẽ dừng lại tại đây để bạn kiểm tra docker/service.")
        raise RuntimeError("External services are offline.")

    print("--------------------------------------------------")
    print("=== [SYSTEM] Dịch vụ nền OK! Bắt đầu nạp Knowledge Base... ===")

    try:
        app.state.knowledge_base = load_knowledge_base()

        # Load dữ liệu bộ PC (Pc_build_data.csv)
        try:
            _build_csv = Path(Config.PC_STORE_DATA) / 'Pc_build_data.csv'
            app.state.build_data = pd.read_csv(_build_csv)
            print(f"=== [HỆ THỐNG] Đã load {len(app.state.build_data)} bộ PC từ Pc_build_data.csv ===")
        except Exception as build_err:
            app.state.build_data = None
            print(f"⚠️ [HỆ THỐNG] Không load được dữ liệu bộ PC: {build_err}")

        print(f"=== [HỆ THỐNG] Gộp thành công! Tổng số linh kiện: {len(app.state.knowledge_base)} dòng. ===")
        print(f"=== [SYSTEM] EMBEDDING MODEL: {EMBEDDING_MODEL_NAME} | DEVICE: {EMBEDDING_DEVICE} ===")

        # Khởi tạo Vector DB nếu chưa có
        print("=== [SYSTEM] Checking Vector DB... ===")
        try:
            initialize_vector_db()
        except Exception as db_err:
            print(f"❌ LỖI TẠO VECTOR DB: {db_err}")

        # Nạp Chroma DB vào RAM
        print(f"=== [SYSTEM] Loading Embedding Model '{Config.EMBEDDING_MODEL}' to {Config.EMBEDDING_DEVICE}... ===")
        import torch
        if Config.EMBEDDING_DEVICE == 'cuda' and torch.cuda.is_available():
            torch.cuda.empty_cache()

        embeddings = HuggingFaceEmbeddings(
            model_name=Config.EMBEDDING_MODEL,
            model_kwargs={"device": Config.EMBEDDING_DEVICE, "local_files_only": Config.EMBEDDING_LOCAL_FILES_ONLY},
            encode_kwargs={"batch_size": 8} # Tránh spike RAM khi search
        )
        # Test thử gọi hàm chạy embedding xem có nổ VRAM không
        embeddings.embed_query("test")
        print("=== [SYSTEM] Embedding Model ready. Loading Chroma DB... ===")
        app.state.vector_store = Chroma(
            persist_directory=Config.VECTOR_DB_DIR, 
            embedding_function=embeddings
        )
        print("=== [SYSTEM] Successfully loaded Chroma Vector DB! ===")
        print("=== [SYSTEM] Server initialization complete! Ready for API requests. ===\n")

    except Exception as e:
        print(f"❌ LỖI KHỞI TẠO HỆ THỐNG: {str(e)}")
        raise e

    try:
        yield
    finally:
        print("=== [SYSTEM] Shutting down Server... ===")
        try:
            # Xóa reference tới Chroma và Embeddings model
            if hasattr(app.state, "vector_store"):
                del app.state.vector_store
            
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
            
        print("=== [SYSTEM] Tắt Ollama Server để gỡ kẹt các request đang chạy và giải phóng VRAM... ===")
        import os
        import platform
        if platform.system() == "Windows":
            os.system("taskkill /F /IM ollama_llama_server.exe /T >nul 2>&1")
            os.system("taskkill /F /IM llama-server.exe /T >nul 2>&1")
        else:
            os.system("pkill -9 ollama_llama_server")
            os.system("pkill -9 llama-server")

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    for error in errors:
        loc = error.get("loc", [])
        if "session_id" in loc:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Validation Error",
                    "message": "Lỗi hệ thống. Vui lòng xóa phiên chat và thử lại!",
                    "code": "INVALID_SESSION_ID"
                }
            )
    
    # Nếu không phải lỗi session_id, trả về 422 mặc định của FastAPI
    return JSONResponse(
        status_code=422,
        content={"detail": errors}
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
