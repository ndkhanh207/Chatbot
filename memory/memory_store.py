# memory/memory_store.py
"""
Persistent chat history dùng MySQL + SQLAlchemy trực tiếp.
"""

from datetime import datetime
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, trim_messages
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime
)
from sqlalchemy.orm import declarative_base, sessionmaker
from config.config import MYSQL_CONNECTION_STRING

# ──────────────────────────────────────────────
# SQLAlchemy setup
# ──────────────────────────────────────────────
Base = declarative_base()


class ChatMessage(Base):
    """Bảng lưu từng message trong hội thoại."""
    __tablename__ = "chat_history"

    id         = Column(Integer,     primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False,   index=True)
    role       = Column(String(10),  nullable=False)   # "human" | "ai"
    content    = Column(Text(length=65535), nullable=False)
    created_at = Column(DateTime,   default=datetime.utcnow)


# Tạo engine + bảng ngay khi import
engine = create_engine(
    MYSQL_CONNECTION_STRING,
    pool_pre_ping=True,   # tự reconnect nếu connection chết
    pool_recycle=3600,    # recycle connection sau 1 giờ
    echo=False,           # đổi True nếu muốn xem SQL log
)
Base.metadata.create_all(engine)  # tạo bảng nếu chưa có
SessionLocal = sessionmaker(bind=engine)

MAX_CHARS = 2000


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _count_chars(messages: list[BaseMessage]) -> int:
    return sum(len(str(m.content)) for m in messages)


def _load_messages(session_id: str) -> list[BaseMessage]:
    """Đọc tất cả messages của session từ MySQL."""
    with SessionLocal() as db:
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
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


# ──────────────────────────────────────────────
# Public API — giữ nguyên interface cũ
# ──────────────────────────────────────────────
def get_trimmed_history(session_id: str) -> list[BaseMessage]:
    """Trả về lịch sử đã trim theo MAX_CHARS."""
    messages = _load_messages(session_id)

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


def save_message(session_id: str, user_msg: str, ai_msg: str) -> None:
    """Lưu một lượt hội thoại vào MySQL."""
    with SessionLocal() as db:
        db.add(ChatMessage(
            session_id=session_id,
            role="human",
            content=user_msg,
        ))
        db.add(ChatMessage(
            session_id=session_id,
            role="ai",
            content=ai_msg,
        ))
        db.commit()


def clear_session(session_id: str) -> None:
    """Xóa toàn bộ lịch sử của một session."""
    with SessionLocal() as db:
        db.query(ChatMessage)\
          .filter(ChatMessage.session_id == session_id)\
          .delete()
        db.commit()