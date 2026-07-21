from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal

from app.catalog.catalog import ShopCatalog
from app.pc_builder.context import PcBuildContext, PcBuildStatus
from app.pc_builder.models import PcBuildCommand

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

async def merge_command_into_context(
    current: PcBuildContext,
    command: PcBuildCommand,
    catalog: ShopCatalog,
) -> StateMergeResult:
    # Clone the context to avoid mutating original immediately if errors occur
    next_state = current.model_copy(deep=True)
    
    if command.action == "reset" or command.action == "create":
        next_state.budget = None
        next_state.purpose = None
        next_state.quantity = 1
        next_state.required_components = {}
        next_state.preferred_components = {}
        next_state.excluded_brands = []
        next_state.build_id = None
        next_state.pending_question = None
        next_state.status = PcBuildStatus.COLLECTING
    
    if command.quantity is not None:
        next_state.quantity = command.quantity
        
    if command.budget is not None:
        # User explicitly mentioned budget scope
        qty = next_state.quantity
        if qty > 1:
            if command.budget_scope == "total":
                next_state.budget = command.budget // qty
            elif command.budget_scope == "per_unit":
                next_state.budget = command.budget
            else:
                return StateMergeResult(
                    next_state=next_state,
                    has_errors=True,
                    clarification_question=f"Ngân sách {command.budget:,} đồng là tổng cho {qty} bộ hay là ngân sách cho mỗi bộ?".replace(",", ".")
                )
        else:
            next_state.budget = command.budget

    if command.purpose is not None:
        next_state.purpose = command.purpose
        
    if command.keep_components:
        for cat in command.keep_components:
            if cat in next_state.required_components:
                # the keep logic just means we don't clear it.
                pass
                
    if command.required_components:
        for cat, val in command.required_components.items():
            next_state.required_components[cat] = val
            
    if command.preferred_components:
        for cat, vals in command.preferred_components.items():
            next_state.preferred_components[cat] = vals
            
    if command.excluded_brands:
        next_state.excluded_brands = list(set(next_state.excluded_brands + command.excluded_brands))

    if command.action == "alternative":
        pass

    next_state.status = PcBuildStatus.COLLECTING
        
    # -------------------------------------------------------------
    # RAG / RESOLUTION
    # Convert raw LLM strings into canonical catalog names so that
    # strict retrieval (search_builds) doesn't fail on "i9 14900k" vs "Core i9-14900K".
    # -------------------------------------------------------------
    from app.catalog.lookup import resolve_component
    
    resolved_required = {}
    for cat, name in next_state.required_components.items():
        comp = resolve_component(name, cat, catalog)
        if not comp:
            from app.pc_builder.reranker import write_build_response
            msg = await write_build_response(
                mode="unavailable",
                facts={"components": {cat: name}}
            )
            return StateMergeResult(
                next_state=current,
                has_errors=True,
                clarification_question=msg
            )
        resolved_required[cat] = comp["name"]

    # Immutable updates following coding standards
    next_state.required_components = {**next_state.required_components, **resolved_required}

    # Note: keep_components is collected by extractor but deliberately ignored in this simple merge strategy. 
    # Component retention is implicit (we don't delete keys unless explicit action="reset").
    
    # -------------------------------------------------------------
    # VALIDATION (The missing piece the user wanted)
    # Check if the requested required_components are physically possible 
    # by querying the catalog. If catalog returns 0 builds, they are either
    # incompatible (e.g. Intel CPU + AMD Main) or we don't sell them.
    # -------------------------------------------------------------
    if next_state.required_components:
        from app.catalog.models import BuildQuery, BuildConstraints
        
        query = BuildQuery(
            # Omit budget to only test if components can physically coexist
            constraints=BuildConstraints(
                required_components=next_state.required_components,
            ),
            limit=1
        )
        candidates = catalog.search_builds(query)
        if not candidates:
            from app.pc_builder.reranker import write_build_response
            
            comps = {k: v for k, v in next_state.required_components.items()}
            msg = await write_build_response(
                mode="unavailable",
                facts={"components": comps}
            )
            return StateMergeResult(
                next_state=current,
                has_errors=True,
                clarification_question=msg
            )
            
    return StateMergeResult(next_state=next_state)
