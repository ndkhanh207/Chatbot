from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum

from app.pc_builder.policy import PendingQuestion

class PcBuildStatus(str, Enum):
    IDLE = "idle"
    COLLECTING = "collecting"
    CONFIGURED = "configured"
    SELECTED = "selected"


from app.pc_builder.policy import PendingQuestion

BudgetScope = Literal["unspecified", "per_unit", "total"]

class PcBuildContext(BaseModel):
    """Deep module state for PC Builder multi-turn context."""
    schema_version: int = 8

    status: PcBuildStatus = PcBuildStatus.IDLE
    build_id: str | None = None
    budget: int | None = None
    quantity: int = Field(default=1, ge=1)
    purpose: str | None = None

    required_components: dict[str, str] = Field(default_factory=dict)
    preferred_components: dict[str, list[str]] = Field(default_factory=dict)
    excluded_brands: list[str] = Field(default_factory=list)

    pending_question: PendingQuestion | None = None

def get_unit_budget(ctx: PcBuildContext) -> int | None:
    # After state merge, ctx.budget is ALWAYS the per-unit budget.
    return ctx.budget
