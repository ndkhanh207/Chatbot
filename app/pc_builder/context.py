from pydantic import BaseModel, Field
from typing import Literal

from app.pc_builder.policy import PendingQuestion
from app.memory.context_manager import ConversationContext

BudgetScope = Literal["unspecified", "per_unit", "total"]

class PcBuildContext(BaseModel):
    """Deep module state for PC Builder multi-turn context."""
    schema_version: int = 8

    build_id: str | None = None
    budget: int | None = None
    quantity: int = Field(default=1, ge=1)
    purpose: str | None = None

    required_components: dict[str, str] = Field(default_factory=dict)
    preferred_components: dict[str, list[str]] = Field(default_factory=dict)
    excluded_brands: list[str] = Field(default_factory=list)

    pending_question: PendingQuestion | None = None

def migrate_pc_build_context(raw: dict) -> dict:
    version = int(raw.get("schema_version", 1))

    if version < 9:
        raw.setdefault("quantity", 1)
        raw.setdefault("purpose", None)
        raw.setdefault("required_components", {})
        raw.setdefault("preferred_components", {})
        raw.setdefault("excluded_brands", [])
        
        # Cleanup old fields to avoid warning
        for field in ["preset_id", "budget_scope", "acceptable_components", "excluded_components", 
                      "mandatory_brands", "preferred_brands", "clarification_count", 
                      "seen_build_ids", "excluded_build_ids", "last_suggested_cpu", 
                      "last_suggested_gpu", "last_suggested_mainboard"]:
            raw.pop(field, None)
            
        raw["schema_version"] = 9

    return raw

def get_unit_budget(ctx: PcBuildContext) -> int | None:
    # After state merge, ctx.budget is ALWAYS the per-unit budget.
    return ctx.budget

class ConversationMemory:
    """Deep Module adapter managing session state over the database."""
    def __init__(self, user_uid: str, session_id: str):
        self.context = ConversationContext(user_uid, session_id)

    def load_context(self) -> PcBuildContext:
        return self.context.load_snapshot(PcBuildContext)

    def commit_turn(self, user_msg: str, ai_msg: str, ctx: PcBuildContext) -> None:
        self.context.commit(
            user_msg, 
            ai_msg, 
            ctx.model_dump(exclude_none=True),
        )
