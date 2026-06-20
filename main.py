"""FastAPI application entry point."""

import asyncio
import pandas as pd
import anyio
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
# Lifespan
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global KNOWLEDGE_BASE, VECTOR_STORE
    print("=== [HỆ THỐNG] Đang khởi tạo Kho tri thức từ structure_data... ===")

    try:
        KNOWLEDGE_BASE = load_knowledge_base()

        print(f"=== [HỆ THỐNG] Gộp thành công! Tổng số linh kiện: {len(KNOWLEDGE_BASE)} dòng. ===")
        print(f"=== [HỆ THỐNG] EMBEDDING MODEL: {EMBEDDING_MODEL_NAME} | DEVICE: {EMBEDDING_DEVICE} ===")

        # Khởi tạo Vector DB nếu chưa có
        try:
            initialize_vector_db()
        except Exception as db_err:
            print(f"❌ LỖI TẠO VECTOR DB: {db_err}")

        # Nạp Chroma DB vào RAM
        embeddings = HuggingFaceEmbeddings(
            model_name=Config.EMBEDDING_MODEL,
            model_kwargs={"device": Config.EMBEDDING_DEVICE}
        )
        VECTOR_STORE = Chroma(
            persist_directory=Config.VECTOR_DB_DIR, 
            embedding_function=embeddings
        )
        print("=== [HỆ THỐNG] Đã nạp thành công Chroma Vector DB! ===")

        print("=== [HỆ THỐNG] Khởi tạo hệ thống Server hoàn tất! Sẵn sàng nhận API. ===")

    except Exception as e:
        print(f"❌ LỖI KHỞI TẠO HỆ THỐNG: {str(e)}")

    yield
    print("=== [HỆ THỐNG] Đang tắt Server... ===")


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
# POST /chat — tạo một "message" mới trong session, trả lời chatbot
# Body JSON thay cho query params (chuẩn REST: dữ liệu thuộc body, không phải URL)
# ──────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(payload: ChatRequest):
    if KNOWLEDGE_BASE is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hệ thống chưa khởi tạo xong, vui lòng thử lại sau."
        )

    try:
        # ⭐ FIX QUAN TRỌNG: truyền hàm trần (không gọi ()) + args riêng,
        # để run_sync thực thi nó trong thread riêng — không block event loop.
        # Trước đây code gọi chat_with_bot(...) ngay lập tức rồi đưa KẾT QUẢ
        # (chuỗi string) vào run_sync, khiến toàn bộ logic chạy đồng bộ trên
        # event loop chính và timeout hoàn toàn không có tác dụng.
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
        # handle_chat trả về dict {"chatbot_reply": "..."}
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
# GET /search — tra cứu, đúng ngữ nghĩa REST cho thao tác đọc (không đổi state)
# Giữ query params vì đây là filter/search, không phải tạo resource
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
# GET /unit-conversions — thao tác tính toán thuần (không phải resource, GET hợp lý)
# ──────────────────────────────────────────────
@app.get("/unit-conversions", response_model=ConvertResponse)
def convert(value: float, from_unit: str, to_unit: str):
    try:
        result = convert_unit(value, from_unit, to_unit)
        return ConvertResponse(result=result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────────────────────────
# DELETE /sessions/{session_id} — xóa resource "session"
# (đổi route cho đúng resource-oriented: session là resource, không phải "history")
# ──────────────────────────────────────────────
@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str):
    clear_session(session_id)
    return None