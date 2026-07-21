from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from pydantic import BaseModel
from app.chat.models import ChatResult
from app.pc_builder.context import PcBuildContext


@dataclass(frozen=True, slots=True)
class VersionedPcContext:
    context: PcBuildContext
    version: int


class PcContextRepository(Protocol):
    async def load(
        self,
        user_uid: str,
        session_id: str,
    ) -> VersionedPcContext:
        ...

    async def save(
        self,
        user_uid: str,
        session_id: str,
        context: PcBuildContext,
        *,
        expected_version: int,
    ) -> int:
        ...


class PcBuildOutcome(BaseModel):
    result: ChatResult
    next_context: PcBuildContext
    state_changed: bool = False
