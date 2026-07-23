from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.chat.models import ChatResult


class PcBuildStatus(str, Enum):
    IDLE = "idle"
    COLLECTING = "collecting"
    CONFIGURED = "configured"
    SELECTED = "selected"


class PendingQuestion(str, Enum):
    GENERAL = "general"
    BUDGET = "budget"
    PURPOSE = "purpose"
    BUDGET_SCOPE = "budget_scope"
    CLARIFICATION = "clarification"
    DROP_CONSTRAINT = "drop_constraint"


class PcBuildAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    ALTERNATIVE = "alternative"
    RESET = "reset"
    QUESTION_CURRENT_BUILD = "question_current_build"


ComponentCategory = Literal["cpu", "gpu", "mainboard"]
BudgetScope = Literal["total", "per_unit", "unknown", "unspecified"]


class PcBuildContext(BaseModel):
    """Deep module state for PC Builder multi-turn context."""
    schema_version: int = 8
    
    status: PcBuildStatus = PcBuildStatus.IDLE
    build_id: str | None = None
    budget: int | None = None
    quantity: int = Field(default=1, ge=1)
    purpose: str | None = None
    purpose_status: Literal["ready", "clarify"] | None = None

    required_components: dict[str, str] = Field(default_factory=dict)
    preferred_components: dict[str, list[str]] = Field(default_factory=dict)
    excluded_brands: list[str] = Field(default_factory=list)

    pending_question: PendingQuestion | None = None


class PcBuildCommand(BaseModel):
    action: PcBuildAction = PcBuildAction.UPDATE

    budget: int | None = None
    budget_scope: BudgetScope = "unknown"
    purpose: str | None = None
    purpose_status: Literal["ready", "clarify"] | None = None
    quantity: int | None = Field(default=None, ge=1, le=100)

    required_components: dict[str, str] = Field(default_factory=dict)
    preferred_components: dict[str, list[str]] = Field(default_factory=dict)
    excluded_brands: list[str] = Field(default_factory=list)
    keep_components: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PcBuildPolicy:
    history_message_limit: int = 6
    retrieval_limit: int = 10


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


def get_unit_budget(ctx: PcBuildContext) -> int | None:
    # After state merge, ctx.budget is ALWAYS the per-unit budget.
    return ctx.budget
