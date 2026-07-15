"""Single interface for conversation history and structured state."""

from typing import TypeVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from app.memory import memory_store


SnapshotT = TypeVar("SnapshotT", bound=BaseModel)
CONTEXT_VERSION = 1


class ConversationContext:
    """Own one user's session history, snapshots, and lifecycle."""

    def __init__(self, user_uid: str, session_id: str):
        self.user_uid = user_uid
        self.session_id = session_id

    def history(self) -> list[BaseMessage]:
        return memory_store.get_trimmed_history(self.user_uid, self.session_id)

    def load_snapshot(self, model: type[SnapshotT]) -> SnapshotT:
        fields = set(model.model_fields)
        for state in memory_store.get_recent_metadata(self.user_uid, self.session_id):
            candidate = {key: value for key, value in state.items() if key in fields}
            if candidate:
                try:
                    return model.model_validate(candidate)
                except Exception as exc:
                    print(f"⚠️ [CONTEXT] Bỏ qua snapshot không hợp lệ: {exc}")
        return model()

    def commit(self, user_message: str, assistant_message: str, state: dict | None = None) -> None:
        normalized = memory_store.normalize_context_metadata(state)
        metadata = {"context_version": CONTEXT_VERSION, "state": normalized}
        memory_store.save_message(
            self.user_uid,
            self.session_id,
            user_message,
            assistant_message,
            metadata=metadata,
        )

    def clear(self) -> None:
        memory_store.clear_session(self.user_uid, self.session_id)
