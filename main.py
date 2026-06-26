"""FastAPI application entry point."""

import asyncio
import pandas as pd
import anyio
import ollama  # Import để check status
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from config.config import EMBEDDING_MODEL as EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE, Config
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from data.data_loader import load_knowledge_base, initialize_vector_db
from app.search_engine import hybrid_search
from app.chat_handler import handle_chat
from tool.calculator import convert_unit
from memory.memory_store import clear_session

# ──────────────────────────────────────────────
# Global state – populated during lifespan startup
# ──────────────────────────────────────────────
KNOWLEDGE_BASE = None
VECTOR_STORE = None

CHAT_TIMEOUT_SECONDS = 30.0


# ──────────────────────────────────────────────
# DEPENDENCY HEALTH CHECKS (Hàm bổ sung)
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
        # LƯU Ý: Đoạn này tùy thuộc vào thư viện bạn đang dùng (pymysql, mysql-connector, hay SQLAlchemy)
        # Cách 1: Nếu bạn dùng PyMySQL trực tiếp:
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
        
        # Cách 2: Nếu bạn dùng SQLAlchemy Engine (Bỏ comment nếu dùng):
        # from database.mysql import engine
        # with engine.connect() as conn:
        #     conn.execute("SELECT 1")

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
    global KNOWLEDGE_BASE, VECTOR_STORE
    print("\n=== 🚀 [SYSTEM STARTUP] TRẠM KIỂM TRA HỆ THỐNG ===")

    # 1. Kiểm tra các dịch vụ cứng trước khi load dữ liệu nặng vào RAM
    ollama_ok = await check_ollama_status()
    mysql_ok = await check_mysql_status()

    if not ollama_ok or not mysql_ok:
        print("❌ [CRITICAL] KHỞI ĐỘNG THẤT BẠI: Một số dịch vụ nền (Ollama/MySQL) chưa sẵn sàng!")
        print("⚠️ Hệ thống sẽ dừng lại tại đây để bạn kiểm tra docker/service.")
        # Throw lỗi để giải tán app ngay tại trận, tránh treo máy vô ích
        raise RuntimeError("External services are offline.")

    print("--------------------------------------------------")
    print("=== [SYSTEM] Dịch vụ nền OK! Bắt đầu nạp Knowledge Base... ===")

    try:
        KNOWLEDGE_BASE = load_knowledge_base()

        print(f"=== [SYSTEM] Initialization complete! Total records: {len(KNOWLEDGE_BASE)}. ===")
        print(f"=== [SYSTEM] EMBEDDING MODEL: {EMBEDDING_MODEL_NAME} | DEVICE: {EMBEDDING_DEVICE} ===")

        # Khởi tạo Vector DB nếu chưa có
        print("=== [SYSTEM] Checking Vector DB... ===")
        try:
            initialize_vector_db()
        except Exception as db_err:
            print(f"❌ LỖI TẠO VECTOR DB: {db_err}")

        # Nạp Chroma DB vào RAM
        print(f"=== [SYSTEM] Loading Embedding Model '{Config.EMBEDDING_MODEL}' to {Config.EMBEDDING_DEVICE}... ===")
        embeddings = HuggingFaceEmbeddings(
            model_name=Config.EMBEDDING_MODEL,
            model_kwargs={"device": Config.EMBEDDING_DEVICE}
        )
        print("=== [SYSTEM] Embedding Model ready. Loading Chroma DB... ===")
        VECTOR_STORE = Chroma(
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


app = FastAPI(lifespan=lifespan)


# ──────────────────────────────────────────────
# Request / Response schemas
# ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    user_message: str = Field(..., min_length=1, description="Câu hỏi của khách hàng")
    session_id: str = Field(..., min_length=1, description="ID phiên chat")


class ChatResponse(BaseModel):
    chatbot_reply: str


class ConvertResponse(BaseModel):
    result: float


# ──────────────────────────────────────────────
# POST /chat
# ──────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(payload: ChatRequest):
    if KNOWLEDGE_BASE is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hệ thống chưa khởi tạo xong, vui lòng thử lại sau."
        )

    try:
        result = await asyncio.wait_for(
            anyio.to_thread.run_sync(
                handle_chat,
                payload.user_message,
                KNOWLEDGE_BASE,
                VECTOR_STORE,
                payload.session_id,
            ),
            timeout=CHAT_TIMEOUT_SECONDS,
        )
        return ChatResponse(chatbot_reply=result["chatbot_reply"])

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Dạ, hệ thống đang bận, bạn thử lại sau nhé!"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Đã xảy ra lỗi hệ thống: {str(e)}"
        )


# ──────────────────────────────────────────────
# GET /search
# ──────────────────────────────────────────────
@app.get("/search")
def search_knowledge_base(q: str = None, category: str = None, top_k: int = 5):
    if KNOWLEDGE_BASE is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kho tri thức chưa được nạp."
        )
    return hybrid_search(q, category, top_k, KNOWLEDGE_BASE, VECTOR_STORE)


# ──────────────────────────────────────────────
# GET /unit-conversions
# ──────────────────────────────────────────────
@app.get("/unit-conversions", response_model=ConvertResponse)
def convert(value: float, from_unit: str, to_unit: str):
    try:
        result = convert_unit(value, from_unit, to_unit)
        return ConvertResponse(result=result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────────────────────────
# DELETE /sessions/{session_id}
# ──────────────────────────────────────────────
@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str):
    clear_session(session_id)
    return None