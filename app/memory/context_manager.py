"""Single interface for conversation history and structured state."""

from typing import TypeVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from app.memory import memory_store


SnapshotT = TypeVar("SnapshotT", bound=BaseModel)
CONTEXT_VERSION = 1


def recent_user_messages(
    messages: list[BaseMessage],
    limit: int = 3,
) -> list[BaseMessage]:
    """Return user-authored context only; generated replies are not model input."""
    if limit <= 0:
        return []
    return [message for message in messages if message.type == "human"][-limit:]


def recent_routing_turns(
    messages: list[BaseMessage],
    limit: int = 3,
) -> list[str]:
    """Prior user text plus the planner-selected handler; never assistant prose."""
    turns = []
    pending_user = None
    for message in messages:
        if message.type == "human":
            pending_user = message.content
            continue
        if message.type != "ai" or pending_user is None:
            continue
        handler = message.additional_kwargs.get("intent")
        suffix = f" [previous_handler={handler}]" if handler else ""
        turns.append(f"user{suffix}: {pending_user}")
        pending_user = None

    if pending_user is not None:
        turns.append(f"user: {pending_user}")
    return turns[-limit:] if limit > 0 else []


def latest_routing_handler(messages: list[BaseMessage]) -> str | None:
    for message in reversed(messages):
        if message.type == "ai" and message.additional_kwargs.get("intent"):
            return str(message.additional_kwargs["intent"])
    return None


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
