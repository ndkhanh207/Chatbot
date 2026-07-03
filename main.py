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
from app.guard.security import limiter

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

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

# ──────────────────────────────────────────────
# DEPENDENCY HEALTH CHECKS
# ──────────────────────────────────────────────
async def check_ollama_status() -> bool:
    """Kiểm tra dịch vụ Ollama đã bật chưa."""
    print("🔄 [SYSTEM] Checking Ollama service status...")
    try:
        # Chạy ollama.list() trong thread riêng để tránh block event loop
        await anyio.to_thread.run_sync(ollama.list)
        print("✅ [SYSTEM] Ollama service is UP and RUNNING!")
        return True
    except Exception as e:
        print(f"❌ [SYSTEM] Ollama check FAILED: Dịch vụ chưa bật hoặc lỗi kết nối! Chi tiết: {e}")
        return False


async def check_mysql_status() -> bool:
    """Kiểm tra kết nối tới cơ sở dữ liệu MySQL."""
    print("🔄 [SYSTEM] Checking MySQL connection...")
    try:
        import pymysql
        connection = pymysql.connect(
            host=Config.MYSQL_HOST,
            port=int(Config.MYSQL_PORT),  # Ép kiểu sang int vì trong config đang là chuỗi
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            connect_timeout=5
        )
        connection.close()

        print("✅ [SYSTEM] MySQL database is UP and RUNNING!")
        return True
    except Exception as e:
        print(f"❌ [SYSTEM] MySQL check FAILED: Không thể kết nối DB! Chi tiết: {e}")
        return False


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
            model_kwargs={"device": Config.EMBEDDING_DEVICE},
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

    yield
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

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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