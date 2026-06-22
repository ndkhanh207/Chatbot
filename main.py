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
from pathlib import Path
import pandas as pd
from fastapi import FastAPI
from contextlib import asynccontextmanager
from sentence_transformers import SentenceTransformer
from config import EMBEDDING_MODEL as EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE

from app.core.data_loader import load_compatibility_rules, load_knowledge_base, initialize_vector_db
from app.core.search_engine import build_corpus_embeddings

# ──────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=== [HỆ THỐNG] Đang khởi tạo Kho tri thức từ structure_data... ===")

    try:
        app.state.knowledge_base = load_knowledge_base()
        app.state.compatibility_rules = load_compatibility_rules()

        # Load dữ liệu bộ PC (Pc_build_data_cleaned.csv)
        try:
            _build_csv = Path(__file__).resolve().parent / 'data' / 'Pc_build_data_cleaned.csv'
            app.state.build_data = pd.read_csv(_build_csv)
            print(f"=== [HỆ THỐNG] Đã load {len(app.state.build_data)} bộ PC từ Pc_build_data_cleaned.csv ===")
        except Exception as build_err:
            app.state.build_data = None
            print(f"⚠️ [HỆ THỐNG] Không load được dữ liệu bộ PC: {build_err}")

        print(f"=== [HỆ THỐNG] Gộp thành công! Tổng số linh kiện: {len(app.state.knowledge_base)} dòng. ===")
        print(f"=== [HỆ THỐNG] Nạp thành công {len(app.state.compatibility_rules)} quy tắc tương thích! ===")
        print("=== [HỆ THỐNG] Đang nạp Model Embedding và số hóa dữ liệu lên RAM... ===")
        print(f"=== [HỆ THỐNG] EMBEDDING MODEL: {EMBEDDING_MODEL_NAME} | DEVICE: {EMBEDDING_DEVICE} ===")

        app.state.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=EMBEDDING_DEVICE)

        def _row_to_text(row):
            parts = [f"Danh mục: {row.get('category', 'UNKNOWN')}"]
            for col, val in row.items():
                if col not in ['category', 'search_text'] and pd.notna(val) and val != "":
                    parts.append(f"{col}: {val}")
            return " ".join(parts)

        corpus_texts = app.state.knowledge_base.apply(_row_to_text, axis=1).tolist()
        app.state.corpus_embeddings = build_corpus_embeddings(app.state.embedding_model, corpus_texts)

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

# Import and include the API routers
from app.api.chat import router as chat_router
app.include_router(chat_router)