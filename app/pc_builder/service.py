import logging
from enum import Enum
from pydantic import BaseModel, Field

from app.catalog import ShopCatalog, BuildRecord
from app.catalog.lookup import resolve_component
from app.catalog.models import BuildQuery, BuildConstraints
from app.chat.models import ChatResult
from app.pc_builder.models import (
    PcBuildContext,
    get_unit_budget,
    PcBuildPolicy,
    PendingQuestion,
    PcBuildOutcome,
    PcBuildCommand,
    PcBuildAction,
    PcBuildStatus,
)
from app.pc_builder.selector import PcBuildSelector, PcBuildSelectionRequest
from app.pc_builder.formatter import format_build_context, render_selected_build_reply
from app.responses import response_renderer, ResponseCode
from app.rag.generator import generate_grounded_answer
from app.rag.models import GroundedAnswerRequest, EvidencePackage, EvidenceItem

logger = logging.getLogger(__name__)

# --- Pure State Helpers ---

def _has_workload_direction(ctx: PcBuildContext) -> bool:
    return any((ctx.required_components, ctx.preferred_components))

def _clear_satisfied_pending_question(ctx: PcBuildContext) -> None:
    pending = ctx.pending_question
    has_workload_direction = _has_workload_direction(ctx)
    if pending in (PendingQuestion.BUDGET, PendingQuestion.BUDGET_SCOPE):
        if ctx.budget is not None:
            ctx.pending_question = None
    elif pending == PendingQuestion.PURPOSE:
        if ctx.purpose or has_workload_direction:
            ctx.pending_question = None
    elif pending == PendingQuestion.GENERAL:
        if ctx.budget is not None and (ctx.purpose or has_workload_direction):
            ctx.pending_question = None

def _contexts_equal(a: PcBuildContext, b: PcBuildContext) -> bool:
    return a.model_dump(mode="json") == b.model_dump(mode="json")

# --- Command Application ---

class PcBuildIssueCode(str, Enum):
    COMPONENT_NOT_FOUND = "component_not_found"
    COMPONENTS_INCOMPATIBLE = "components_incompatible"
    BUDGET_SCOPE_AMBIGUOUS = "budget_scope_ambiguous"

class PcBuildIssue(BaseModel):
    code: PcBuildIssueCode
    facts: dict[str, object] = Field(default_factory=dict)

class StateMergeResult(BaseModel):
    next_state: PcBuildContext
    issues: list[PcBuildIssue] = Field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.issues) > 0

async def _merge_command(
    *,
    current: PcBuildContext,
    command: PcBuildCommand,
    catalog: ShopCatalog,
) -> StateMergeResult:
    next_state = current.model_copy(deep=True)
    
    if command.action in (PcBuildAction.RESET, PcBuildAction.CREATE):
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
        qty = next_state.quantity
        if qty > 1:
            if command.budget_scope == "total":
                next_state.budget = command.budget // qty
            elif command.budget_scope == "per_unit":
                next_state.budget = command.budget
            else:
                return StateMergeResult(
                    next_state=next_state,
                    issues=[PcBuildIssue(
                        code=PcBuildIssueCode.BUDGET_SCOPE_AMBIGUOUS,
                        facts={"budget": command.budget, "quantity": qty}
                    )]
                )
        else:
            next_state.budget = command.budget

    if command.purpose is not None:
        next_state.purpose = command.purpose
        if command.purpose_status is not None:
            next_state.purpose_status = command.purpose_status
                
    if command.required_components:
        for cat, val in command.required_components.items():
            next_state.required_components[cat] = val
            
    if command.preferred_components:
        for cat, vals in command.preferred_components.items():
            next_state.preferred_components[cat] = vals
            
    if command.excluded_brands:
        next_state.excluded_brands = list(set(next_state.excluded_brands + command.excluded_brands))

    next_state.status = PcBuildStatus.COLLECTING
        
    resolved_required = {}
    for cat, name in next_state.required_components.items():
        comp = resolve_component(name, cat, catalog)
        if not comp:
            return StateMergeResult(
                next_state=current,
                issues=[PcBuildIssue(
                    code=PcBuildIssueCode.COMPONENT_NOT_FOUND,
                    facts={"category": cat, "name": name}
                )]
            )
        resolved_required[cat] = comp["name"]

    next_state.required_components = {**next_state.required_components, **resolved_required}
    
    if next_state.required_components:
        query = BuildQuery(
            constraints=BuildConstraints(required_components=next_state.required_components),
            limit=1
        )
        candidates = catalog.search_builds(query)
        if not candidates:
            return StateMergeResult(
                next_state=current,
                issues=[PcBuildIssue(
                    code=PcBuildIssueCode.COMPONENTS_INCOMPATIBLE,
                    facts={"components": dict(next_state.required_components)}
                )]
            )
            
    return StateMergeResult(next_state=next_state)

def _build_pc_evidence(build: BuildRecord, purpose: str | None) -> str:
    fields = [
        ("Mục đích sử dụng", purpose),
        ("Mã bộ", build.build_id),
        ("Mục đích được thiết kế", build.detailed_purpose),
        ("Workload chính", build.attributes.get("Primary_Workload")),
        ("Ghi chú", build.notes),
        ("Cấu hình", ", ".join(f"{cat}: {c.model}" for cat, c in build.components.items())),
    ]
    return " | ".join(f"{k}: {v}" for k, v in fields if v)

# --- Service ---

class PcBuildService:
    def __init__(self, *, catalog: ShopCatalog, selector: PcBuildSelector | None = None) -> None:
        self.catalog = catalog
        self.policy = PcBuildPolicy()
        self._selector = selector or PcBuildSelector()

    def _outcome(self, reply: str, ctx: PcBuildContext, original_ctx: PcBuildContext, contexts: list[str] | None = None, handled: bool = True) -> PcBuildOutcome:
        result = ChatResult(
            reply=reply, 
            contexts=contexts or [], 
            handled=handled,
            metadata={'intent': 'build_pc'}
        )
        return PcBuildOutcome(
            result=result,
            next_context=ctx.model_copy(deep=True),
            state_changed=not _contexts_equal(ctx, original_ctx),
        )

    async def _handle_merge_issue(self, issue: PcBuildIssue, ctx: PcBuildContext, original_ctx: PcBuildContext, user_message: str) -> PcBuildOutcome:
        if issue.code == PcBuildIssueCode.BUDGET_SCOPE_AMBIGUOUS:
            budget = issue.facts.get("budget", 0)
            qty = issue.facts.get("quantity", 2)
            budget_str = f"{budget:,}".replace(",", ".")
            reply = response_renderer.render(ResponseCode.BUDGET_SCOPE_AMBIGUOUS, facts={"budget": budget_str, "qty": qty})
            ctx.pending_question = PendingQuestion.CLARIFICATION
            return self._outcome(reply, ctx, original_ctx, contexts=[reply])
            
        elif issue.code == PcBuildIssueCode.COMPONENT_NOT_FOUND:
            name = issue.facts.get("name", "")
            reply = response_renderer.render(ResponseCode.COMPONENT_NOT_FOUND, facts={"name": name})
            ctx.pending_question = PendingQuestion.CLARIFICATION
            return self._outcome(reply, ctx, original_ctx, contexts=[reply])
            
        elif issue.code == PcBuildIssueCode.COMPONENTS_INCOMPATIBLE:
            reply = response_renderer.render(ResponseCode.COMPONENTS_INCOMPATIBLE)
            ctx.pending_question = PendingQuestion.CLARIFICATION
            return self._outcome(reply, ctx, original_ctx, contexts=[reply])
            
        reply = response_renderer.render(ResponseCode.MERGE_ERROR)
        ctx.pending_question = PendingQuestion.CLARIFICATION
        return self._outcome(reply, ctx, original_ctx, contexts=[reply])

    async def _answer_about_current_build(self, ctx: PcBuildContext, original_ctx: PcBuildContext, user_message: str) -> PcBuildOutcome:
        if not ctx.build_id:
            reply = response_renderer.render(ResponseCode.MISSING_SELECTED_BUILD)
            return self._outcome(reply, ctx, original_ctx, contexts=[])

        build = self.catalog.get_build(ctx.build_id)
        if not build:
            reply = response_renderer.render(ResponseCode.BUILD_NOT_FOUND)
            return self._outcome(reply, ctx, original_ctx, contexts=[])

        evidence_str = _build_pc_evidence(build, ctx.purpose)
        evidence = EvidencePackage(
            query=user_message,
            intent="build_pc",
            items=[EvidenceItem(source_id=build.build_id, source_type="build", facts={"details": evidence_str})]
        )
        generation = await generate_grounded_answer(GroundedAnswerRequest(
            user_message=user_message,
            intent="build_pc",
            evidence=evidence,
        ))
        
        reply = generation.value.answer if generation.ok and generation.value else response_renderer.render(ResponseCode.LLM_UNAVAILABLE)
        return self._outcome(reply=reply, ctx=ctx, original_ctx=original_ctx, contexts=[format_build_context(build)])

    async def _build_reply(self, build: BuildRecord, user_message: str, ctx: PcBuildContext, original_ctx: PcBuildContext, selection_reason: str | None = None) -> PcBuildOutcome:
        ctx.build_id = build.build_id
        _clear_satisfied_pending_question(ctx)

        evidence_str = _build_pc_evidence(build, ctx.purpose)
        evidence = EvidencePackage(
            query=user_message,
            intent="build_pc",
            items=[EvidenceItem(source_id=build.build_id, source_type="build", facts={"details": evidence_str})]
        )
        generation = await generate_grounded_answer(GroundedAnswerRequest(
            user_message=user_message,
            intent="build_pc",
            evidence=evidence,
        ))
        
        explanation = generation.value.answer if generation.ok and generation.value else selection_reason
        
        reply = render_selected_build_reply(
            canonical_block=format_build_context(build),
            explanation=explanation,
        )

        return self._outcome(
            reply=reply,
            ctx=ctx,
            original_ctx=original_ctx,
            contexts=[format_build_context(build)],
        )

    async def execute(
        self,
        command: PcBuildCommand,
        current_context: PcBuildContext,
        user_message: str,
    ) -> PcBuildOutcome:
        ctx = current_context.model_copy(deep=True)
        original_ctx = current_context.model_copy(deep=True)

        if command.action == PcBuildAction.QUESTION_CURRENT_BUILD:
            return await self._answer_about_current_build(ctx, original_ctx, user_message)

        merge_result = await _merge_command(
            current=ctx,
            command=command,
            catalog=self.catalog,
        )

        if merge_result.has_errors:
            return await self._handle_merge_issue(merge_result.issues[0], ctx, original_ctx, user_message)

        ctx = merge_result.next_state
        _clear_satisfied_pending_question(ctx)

        has_direction = bool(
            (ctx.purpose and ctx.purpose.strip()) or
            ctx.required_components or
            ctx.preferred_components
        )
        needs_purpose = ctx.purpose_status == "clarify" or not has_direction

        if needs_purpose:
            ctx.pending_question = PendingQuestion.PURPOSE
            code = ResponseCode.MISSING_PURPOSE
                
            reply = response_renderer.render(code)
            return self._outcome(reply, ctx, original_ctx, contexts=[reply])

        constraints = BuildConstraints(
            required_components=ctx.required_components,
            preferred_components=ctx.preferred_components,
            excluded_brands=ctx.excluded_brands,
        )

        unit_budget = get_unit_budget(ctx)
        if unit_budget is not None and unit_budget < 0:
            reply = "Xin lỗi, ngân sách không thể là số âm. Bạn có thể cung cấp mức ngân sách hợp lệ không ạ?"
            return self._outcome(reply, ctx, original_ctx, contexts=[reply])

        excluded_ids = set()
        if command.action == PcBuildAction.ALTERNATIVE and ctx.build_id:
            excluded_ids.add(ctx.build_id)

        query = BuildQuery(
            text=ctx.purpose or user_message,
            budget=unit_budget,
            constraints=constraints,
            excluded_ids=excluded_ids,
            limit=self.policy.retrieval_limit,
        )

        candidates = self.catalog.search_builds(query)

        if not candidates:
            reply = response_renderer.render(ResponseCode.NO_CANDIDATE_BUILD)
            return self._outcome(reply, ctx, original_ctx, contexts=[reply])

        candidates = candidates[:5]

        selection = await self._selector.select(
            request=PcBuildSelectionRequest(
                user_message=user_message,
                purpose=ctx.purpose,
                budget=unit_budget,
            ),
            candidates=candidates,
        )

        selected = next((c for c in candidates if c.build_id == selection.build_id), candidates[0])

        return await self._build_reply(
            selected,
            user_message,
            ctx,
            original_ctx,
            selection_reason=selection.reason,
        )
