from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class DomainRequest(BaseModel):
    user_message: str
    user_uid: str
    session_id: str
    chat_history: list[Any] = Field(default_factory=list)


class ChatResult(BaseModel):
    reply: str
    contexts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    handled: bool = True
