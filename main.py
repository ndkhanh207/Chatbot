"""FastAPI application entry point.

This file is intentionally **thin** – it only wires up the FastAPI app, the
lifespan (startup/shutdown) logic, and the API endpoints.  All business logic
lives in dedicated modules:

* ``model_utils``   – Ollama model selection
* ``search_engine`` – hybrid search & embedding
* ``chat_handler``  – chat endpoint logic
* ``compatibility`` – compatibility‑check helpers
* ``data_loader``   – data loading & Vector DB initialisation
"""

import os
import pandas as pd
import ollama
from fastapi import FastAPI
from contextlib import asynccontextmanager
from sentence_transformers import SentenceTransformer
from langchain_huggingface import HuggingFaceEmbeddings
from config import EMBEDDING_MODEL as EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE, CHAT_MODEL, Config

from data_loader import load_compatibility_rules, load_knowledge_base, convert_to_documents, initialize_vector_db
from search_engine import build_corpus_embeddings, hybrid_search
from chat_handler import handle_chat
from util.model_utils import get_ollama_model
from tool.calculator import convert_unit

# ──────────────────────────────────────────────
# Global state – populated during lifespan startup
# ──────────────────────────────────────────────
KNOWLEDGE_BASE = None
EMBEDDING_MODEL = None
CORPUS_EMBEDDINGS = None
COMPATIBILITY_RULES = None


# ──────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global KNOWLEDGE_BASE, EMBEDDING_MODEL, CORPUS_EMBEDDINGS, COMPATIBILITY_RULES
    print("=== [HỆ THỐNG] Đang khởi tạo Kho tri thức từ structure_data... ===")

    try:
        KNOWLEDGE_BASE = load_knowledge_base()
        COMPATIBILITY_RULES = load_compatibility_rules()

        print(f"=== [HỆ THỐNG] Gộp thành công! Tổng số linh kiện: {len(KNOWLEDGE_BASE)} dòng. ===")
        print(f"=== [HỆ THỐNG] Nạp thành công {len(COMPATIBILITY_RULES)} quy tắc tương thích! ===")
        print("=== [HỆ THỐNG] Đang nạp Model Embedding và số hóa dữ liệu lên RAM... ===")
        print(f"=== [HỆ THỐNG] EMBEDDING MODEL: {EMBEDDING_MODEL_NAME} | DEVICE: {EMBEDDING_DEVICE} ===")

        EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME, device=EMBEDDING_DEVICE)
        # Build a comprehensive text representation for each row to improve
        # semantic search. Previously we only used ``category`` + product name,
        # which meant specifications like "xung cơ bản" or "xung boost" were not
        # part of the embedding space. As a result, queries asking about those
        # specs (e.g., "Base Clock" of a GPU) could not be matched. We now
        # concatenate *all* non‑empty, non‑numeric fields (including the
        # category) into a single string per row.
        def _row_to_text(row):
            parts = []
            # Ensure category is first
            if 'category' in row and pd.notna(row['category']):
                parts.append(str(row['category']))
            for col, val in row.items():
                if col == 'category':
                    continue
                # Include textual and numeric values that are not price
                if col.lower() in ('giá', 'price'):
                    continue
                if pd.isna(val) or val == "" or (isinstance(val, (int, float)) and val == 0):
                    continue
                parts.append(str(val))
            return " ".join(parts)

        corpus_texts = KNOWLEDGE_BASE.apply(_row_to_text, axis=1).tolist()
        CORPUS_EMBEDDINGS = build_corpus_embeddings(EMBEDDING_MODEL, corpus_texts)

        # Khởi tạo hoặc tải Vector DB (Chroma)
        try:
            initialize_vector_db()
        except Exception as db_err:
            print(f"❌ LỖI TẠO VECTOR DB: {db_err}")

        print("=== [HỆ THỐNG] Khởi tạo hệ thống Server hoàn tất! Sẵn sàng nhận API. ===")

    except Exception as e:
        print(f"❌ LỖI KHỞI TẠO HỆ THỐNG: {str(e)}")

    yield
    print("=== [HỆ THỐNG] Đang tắt Server... ===")


app = FastAPI(lifespan=lifespan)


# ──────────────────────────────────────────────
# Internal search helper (used by chat handler)
# ──────────────────────────────────────────────
def _search(q: str = None, category: str = None, top_k: int = 5):
    """Thin wrapper around ``hybrid_search`` that injects the global state."""
    return hybrid_search(q, category, top_k, KNOWLEDGE_BASE, EMBEDDING_MODEL, CORPUS_EMBEDDINGS)


# ──────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────
@app.get('/test-knowledge-base')
def test_kb(q: str = None, category: str = None, top_k: int = 5):
    """API tìm kiếm lai (Hybrid Search)."""
    if KNOWLEDGE_BASE is None:
        return {'status': 'Kho hàng trống!'}
    return _search(q, category, top_k)


@app.get("/chat")
def chat_with_bot(user_message: str):
    """API chatbot hoàn chỉnh với tính năng kiểm tra tương thích."""
    return handle_chat(user_message, KNOWLEDGE_BASE, COMPATIBILITY_RULES, _search)


@app.get("/calculate")
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