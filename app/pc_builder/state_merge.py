from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal

from app.catalog.catalog import ShopCatalog
from app.pc_builder.context import PcBuildContext
from app.pc_builder.extractor import Interpretation

class MergeIssue(BaseModel):
    level: Literal["warning", "error"]
    field: str
    message: str
    candidates: list[str] = Field(default_factory=list)

class StateMergeResult(BaseModel):
    next_state: PcBuildContext
    issues: list[MergeIssue] = Field(default_factory=list)
    has_errors: bool = False
    clarification_question: str | None = None

def apply_interpretation_delta(
    current: PcBuildContext,
    delta: Interpretation,
    catalog: ShopCatalog,
) -> StateMergeResult:
    # Clone the context to avoid mutating original immediately if errors occur
    next_state = current.model_copy(deep=True)
    
    if delta.action == "reset":
        next_state.budget = None
        next_state.purpose = None
        next_state.quantity = 1
        next_state.required_components.clear()
        next_state.preferred_components.clear()
        next_state.excluded_brands.clear()
        next_state.build_id = None
        next_state.pending_question = None
    
    if delta.quantity is not None:
        next_state.quantity = delta.quantity
        
    if delta.budget is not None:
        # User explicitly mentioned budget scope
        qty = next_state.quantity
        if qty > 1:
            if delta.budget_scope == "total":
                next_state.budget = delta.budget // qty
            elif delta.budget_scope == "per_unit":
                next_state.budget = delta.budget
            else:
                return StateMergeResult(
                    next_state=next_state,
                    has_errors=True,
                    clarification_question=f"Ngân sách {delta.budget:,} đồng là tổng cho {qty} bộ hay là ngân sách cho mỗi bộ?".replace(",", ".")
                )
        else:
            next_state.budget = delta.budget

    if delta.purpose is not None:
        next_state.purpose = delta.purpose
        
    next_state.required_components.update(delta.required_components)
    next_state.preferred_components.update(delta.preferred_components)
    
    for brand in delta.excluded_brands:
        if brand not in next_state.excluded_brands:
            next_state.excluded_brands.append(brand)

    # Note: keep_components is collected by extractor but deliberately ignored in this simple merge strategy. 
    # Component retention is implicit (we don't delete keys unless explicit action="reset").
            
    return StateMergeResult(next_state=next_state)
