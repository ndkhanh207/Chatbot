from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from pydantic import BaseModel, Field
from app.chat.models import ChatResult
from app.pc_builder.context import PcBuildContext, PcBuildStatus



from typing import Literal

ComponentCategory = Literal["cpu", "gpu", "mainboard"]
BudgetScope = Literal["total", "per_unit", "unknown"]


class PcBuildAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    ALTERNATIVE = "alternative"
    RESET = "reset"
    QUESTION_CURRENT_BUILD = "question_current_build"


class PcBuildCommand(BaseModel):
    action: PcBuildAction = PcBuildAction.UPDATE

    budget: int | None = None
    budget_scope: BudgetScope = "unknown"
    purpose: str | None = None
    quantity: int | None = Field(default=None, ge=1, le=100)

    required_components: dict[str, str] = Field(default_factory=dict)
    preferred_components: dict[str, list[str]] = Field(default_factory=dict)
    excluded_brands: list[str] = Field(default_factory=list)
    keep_components: list[str] = Field(default_factory=list)


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
