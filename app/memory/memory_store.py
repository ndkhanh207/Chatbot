# memory/memory_store.py
"""
Persistent chat history dùng MySQL + SQLAlchemy trực tiếp.
Lazy init: không kết nối MySQL tại import time — tránh block server startup.
"""

from datetime import datetime
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, trim_messages
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from config.config import MYSQL_CONNECTION_STRING

# ──────────────────────────────────────────────
# SQLAlchemy setup  (lazy — không block import)
# ──────────────────────────────────────────────
Base = declarative_base()


class ChatMessage(Base):
    """Bảng lưu từng message trong hội thoại."""
    __tablename__ = "chat_history"

    id         = Column(Integer,     primary_key=True, autoincrement=True)
    user_uid   = Column(String(255), nullable=False,   index=True)   # Firebase UID để phân biệt user
    session_id = Column(String(255), nullable=False,   index=True)
    role       = Column(String(10),  nullable=False)   # "human" | "ai"
    content    = Column(Text(length=65535), nullable=False)
    created_at = Column(DateTime,   default=datetime.utcnow)


# Lazy init — chỉ kết nối MySQL khi thực sự cần, tránh block server startup
_engine = None
_SessionLocal = None
_db_available = None  # None = chưa thử, True/False = đã thử


def _get_session():
    """Khởi tạo engine + bảng lần đầu gọi. Trả về session hoặc None nếu MySQL lỗi."""
    global _engine, _SessionLocal, _db_available

    if _db_available is False:
        return None

    if _SessionLocal is None:
        try:
            _engine = create_engine(
                MYSQL_CONNECTION_STRING,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
                connect_args={"connect_timeout": 5},  # timeout 5s thay vì treo vô hạn
            )
            # Test kết nối thật trước khi tạo bảng
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(_engine)
            _SessionLocal = sessionmaker(bind=_engine)
            _db_available = True
            print("=== [MEMORY] MySQL kết nối thành công! ===")
        except Exception as e:
            print(f"⚠️ [MEMORY] Không thể kết nối MySQL: {e}")
            print("⚠️ [MEMORY] Chat history sẽ không được lưu trong phiên này.")
            _db_available = False
            return None

    return _SessionLocal()

MAX_CHARS = 2000
MAX_AI_SAVE_LEN = 200  # Rút gọn AI reply trước khi lưu, chống ngộ độc history


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _count_chars(messages: list[BaseMessage]) -> int:
    return sum(len(str(m.content)) for m in messages)


def _load_messages(user_uid: str, session_id: str) -> list[BaseMessage]:
    """Đọc tất cả messages của session từ MySQL."""
    db = _get_session()
    if db is None:
        return []
    try:
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.user_uid == user_uid, ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        messages = []
        for row in rows:
            if row.role == "human":
                messages.append(HumanMessage(content=row.content))
            elif row.role == "ai":
                messages.append(AIMessage(content=row.content))
        return messages
    finally:
        db.close()


# ──────────────────────────────────────────────
# Public API — giữ nguyên interface cũ
# ──────────────────────────────────────────────
def get_trimmed_history(user_uid: str, session_id: str) -> list[BaseMessage]:
    """Trả về lịch sử đã trim theo MAX_CHARS."""
    messages = _load_messages(user_uid, session_id)

    if not messages:
        return []

    return trim_messages(
        messages,
        max_tokens=MAX_CHARS,
        strategy="last",
        token_counter=_count_chars,
        include_system=False,
        allow_partial=False,
    )


def _summarize_for_history(ai_msg: str) -> str:
    """Rút gọn câu trả lời AI trước khi lưu vào history.
    Chỉ giữ phần đầu (~200 ký tự) để reformulate LLM không bị
    nhiễm data sản phẩm/giá cả từ reply cũ (ngộ độc history).
    """
    if len(ai_msg) <= MAX_AI_SAVE_LEN:
        return ai_msg
    # Cắt tại ranh giới câu gần nhất (dấu chấm, xuống dòng)
    truncated = ai_msg[:MAX_AI_SAVE_LEN]
    # Tìm vị trí dấu chấm hoặc xuống dòng cuối cùng trong phạm vi cắt
    for sep in ['. ', '.\n', '\n']:
        pos = truncated.rfind(sep)
        if pos > MAX_AI_SAVE_LEN // 2:  # Chỉ cắt nếu không mất quá nhiều
            truncated = truncated[:pos + 1]
            break
    return truncated.strip()


def save_message(user_uid: str, session_id: str, user_msg: str, ai_msg: str) -> None:
    """Lưu một lượt hội thoại vào MySQL.
    AI reply được rút gọn để tránh ngộ độc history cho reformulate.
    """
    db = _get_session()
    if db is None:
        return
    try:
        ai_short = _summarize_for_history(ai_msg)
        db.add(ChatMessage(
            user_uid=user_uid,
            session_id=session_id,
            role="human",
            content=user_msg,
        ))
        db.add(ChatMessage(
            user_uid=user_uid,
            session_id=session_id,
            role="ai",
            content=ai_short,
        ))
        db.commit()
    finally:
        db.close()


def clear_session(user_uid: str, session_id: str) -> None:
    """Xóa toàn bộ lịch sử của một session theo Firebase UID."""
    db = _get_session()
    if db is None:
        return
    try:
        db.query(ChatMessage)\
          .filter(ChatMessage.user_uid == user_uid, ChatMessage.session_id == session_id)\
          .delete()
        db.commit()
    finally:
        db.close()