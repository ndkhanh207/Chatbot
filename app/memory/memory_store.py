# memory/memory_store.py
"""
Persistent chat history dùng MySQL + SQLAlchemy trực tiếp.
Lazy init: không kết nối MySQL tại import time — tránh block server startup.
"""

from datetime import datetime
import json
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, trim_messages
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, text, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker
from config.config import MYSQL_CONNECTION_STRING, MYSQL_TABLE

# ──────────────────────────────────────────────
# SQLAlchemy setup  (lazy — không block import)
# ──────────────────────────────────────────────
Base = declarative_base()


class ChatMessage(Base):
    """Bảng lưu từng message trong hội thoại."""
    __tablename__ = MYSQL_TABLE

    id            = Column(Integer,     primary_key=True, autoincrement=True)
    user_uid      = Column(String(255), nullable=False,   index=True)   # Firebase UID để phân biệt user
    session_id    = Column(String(255), nullable=False,   index=True)
    role          = Column(String(10),  nullable=False)   # "human" | "ai"
    content       = Column(Text(length=65535), nullable=False)
    metadata_json = Column(JSON,        nullable=True)
    created_at    = Column(DateTime,    default=datetime.utcnow)


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
HISTORY_FETCH_LIMIT = 100
METADATA_FETCH_LIMIT = 20


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _count_chars(messages: list[BaseMessage]) -> int:
    return sum(len(str(m.content)) for m in messages)


def normalize_context_metadata(metadata: dict | None) -> dict:
    """Return one state shape for legacy, intent, and versioned metadata."""
    if not isinstance(metadata, dict):
        return {}

    state = metadata.get("state", metadata)
    if not isinstance(state, dict):
        return {}

    nested = state.get("intent_state")
    if isinstance(nested, dict):
        return {**{k: v for k, v in state.items() if k != "intent_state"}, **nested}
    return state


def _load_messages(user_uid: str, session_id: str) -> list[BaseMessage]:
    """Đọc tất cả messages của session từ MySQL."""
    db = _get_session()
    if db is None:
        return []
    try:
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.user_uid == user_uid, ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.desc())
            .limit(HISTORY_FETCH_LIMIT)
            .all()
        )
        messages = []
        for row in reversed(rows):
            kwargs = normalize_context_metadata(row.metadata_json)
            # ponytail: filter out noise from LLM context window to save tokens and
            # prevent hallucination, but keep them in DB for UI continuity.
            
            # [FIXED]: intent nằm bên trong intent_state do hàm build_intent_metadata tạo ra!
            if kwargs.get("intent") == "none":
                continue
                
            if row.role == "human":
                messages.append(HumanMessage(content=row.content, additional_kwargs=kwargs))
            elif row.role == "ai":
                messages.append(AIMessage(content=row.content, additional_kwargs=kwargs))
        return messages
    except Exception as e:
        print(f"❌ [MEMORY ERROR] Lỗi khi đọc dữ liệu từ Database: {e}")
        return []
    finally:
        db.close()


# ──────────────────────────────────────────────
# Storage adapter used by ConversationContext
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


def get_recent_metadata(user_uid: str, session_id: str) -> list[dict]:
    """Return newest AI context states for snapshot recovery."""
    db = _get_session()
    if db is None:
        return []
    try:
        rows = (
            db.query(ChatMessage.metadata_json)
            .filter(
                ChatMessage.user_uid == user_uid,
                ChatMessage.session_id == session_id,
                ChatMessage.role == "ai",
                ChatMessage.metadata_json != None,
            )
            .order_by(ChatMessage.id.desc())
            .limit(METADATA_FETCH_LIMIT)
            .all()
        )
        return [normalize_context_metadata(row[0]) for row in rows if row[0]]
    except Exception as e:
        print(f"❌ [MEMORY ERROR] Lỗi khi lấy context metadata: {e}")
        return []
    finally:
        db.close()


def _summarize_for_history(ai_msg: str) -> str:
    """Rút gọn câu trả lời AI trước khi lưu vào history.
    Chỉ giữ phần đầu (~200 ký tự) để reformulate LLM không bị
    nhiễm data sản phẩm/giá cả từ reply cũ (ngộ độc history).
    """
    if "[GỢI Ý BỘ PC TỐI ƯU]" in ai_msg or "- Mã bộ:" in ai_msg:
        return ai_msg
    
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


def save_message(user_uid: str, session_id: str, user_msg: str, ai_msg: str, metadata: dict = None) -> None:
    """Lưu một lượt hội thoại vào MySQL.
    AI reply được rút gọn để tránh ngộ độc history cho reformulate.
    metadata được lưu dưới dạng JSON cho AI message để duy trì state.
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
            metadata_json=None,
        ))
        db.add(ChatMessage(
            user_uid=user_uid,
            session_id=session_id,
            role="ai",
            content=ai_short,
            metadata_json=metadata
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"❌ [MEMORY ERROR] Lỗi khi ghi lịch sử chat vào Database: {e}")
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
    except Exception as e:
        db.rollback()
        print(f"❌ [MEMORY ERROR] Lỗi khi xóa session trong Database: {e}")
    finally:
        db.close()
def get_full_history_api(user_uid: str, session_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """Trả về toàn bộ lịch sử dạng list dict cho REST API."""
    db = _get_session()
    if db is None:
        return []
    try:
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.user_uid == user_uid, ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        history = []
        for row in rows:
            history.append({
                "role": row.role,
                "content": row.content,
                "timestamp": row.created_at.isoformat() if row.created_at else None
            })
        return history
    except Exception as e:
        print(f"❌ [MEMORY ERROR] Lỗi khi lấy API history từ Database: {e}")
        return [{"role": "system", "content": f"DB Exception: {e}", "timestamp": None}]
    finally:
        db.close()
