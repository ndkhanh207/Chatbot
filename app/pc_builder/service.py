import logging
from app.pc_builder.context import PcBuildContext, get_unit_budget
from app.pc_builder.reranker import write_build_response, choose_build
from app.pc_builder.state_merge import merge_command_into_context
from app.pc_builder.clarification import (
    clear_satisfied_pending_question,
    evaluate_request_completeness,
)
from app.pc_builder.formatter import (
    format_build_context,
    render_selected_build_reply,
    format_approx_million,
)
from app.pc_builder.policy import PcBuildPolicy, PendingQuestion
from app.catalog.models import BuildQuery, BuildConstraints
from app.chat.models import ChatResult
from app.pc_builder.models import PcBuildOutcome, PcBuildCommand, PcBuildAction
from app.catalog import BuildRecord, ShopCatalog

logger = logging.getLogger(__name__)

class PcBuildService:
    def __init__(
        self,
        *,
        catalog: ShopCatalog,
    ) -> None:
        self.catalog = catalog
        self.policy = PcBuildPolicy()

    def _outcome(self, reply: str, ctx: PcBuildContext, original_ctx: PcBuildContext, contexts: list[str] | None = None, handled: bool = True) -> PcBuildOutcome:
        result = ChatResult(
            reply=reply, 
            contexts=contexts or [], 
            handled=handled,
            metadata={'intent': 'build_pc'}
        )
            
        state_changed = (
            ctx.model_dump(mode='json') != original_ctx.model_dump(mode='json')
        )
        return PcBuildOutcome(
            result=result,
            next_context=ctx.model_copy(deep=True),
            state_changed=state_changed,
        )

    def _early_reply(self, reply: str, ctx: PcBuildContext, original_ctx: PcBuildContext, question: PendingQuestion) -> PcBuildOutcome:
        ctx.pending_question = question
        return self._outcome(reply, ctx, original_ctx, contexts=[reply])

    async def _build_not_found_reply(self, constraints: BuildConstraints, ctx: PcBuildContext, original_ctx: PcBuildContext, user_message: str) -> PcBuildOutcome:
        reply = await write_build_response(
            mode="unavailable",
            facts={"constraints": constraints.model_dump(mode="json")},
            candidates=[],
            user_message=user_message,
        )
        return self._outcome(reply, ctx, original_ctx, contexts=[reply])

    async def _build_reply(self, build: BuildRecord, user_message: str, ctx: PcBuildContext, original_ctx: PcBuildContext) -> PcBuildOutcome:
        ctx.build_id = build.build_id
        clear_satisfied_pending_question(ctx)

        reply = await write_build_response(
            mode="recommendation",
            facts={},
            candidates=[build],
            user_message=user_message,
        )
        
        reply = render_selected_build_reply(
            canonical_block=format_build_context(build),
            explanation=reply,
        )

        return self._outcome(
            reply=reply,
            ctx=ctx,
            original_ctx=original_ctx,
            contexts=[format_build_context(build)],
        )

    async def _answer_about_current_build(self, ctx: PcBuildContext, original_ctx: PcBuildContext, user_message: str) -> PcBuildOutcome:
        if not ctx.build_id:
            reply = "Bạn chưa chọn cấu hình nào cả. Bạn có thể cho mình biết nhu cầu và ngân sách để mình đề xuất nhé."
            return self._outcome(reply, ctx, original_ctx, contexts=[])

        build = self.catalog.get_build(ctx.build_id)
        if not build:
            reply = "Cấu hình bạn đang chọn hiện không còn khả dụng."
            return self._outcome(reply, ctx, original_ctx, contexts=[])

        reply = await write_build_response(
            mode="current_build_qa",
            facts={"build_id": ctx.build_id},
            candidates=[build],
            user_message=user_message,
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

        # Merge command into context
        merge_result = await merge_command_into_context(
            current=ctx,
            command=command,
            catalog=self.catalog,
        )

        if merge_result.has_errors:
            return self._early_reply(
                merge_result.clarification_question
                or "Yêu cầu chưa rõ, bạn nói lại giúp em nhé?",
                ctx,
                original_ctx,
                PendingQuestion.CLARIFICATION,
            )

        ctx = merge_result.next_state
        clear_satisfied_pending_question(ctx)

        clarification = evaluate_request_completeness(ctx)

        if clarification is not None:
            if clarification == PendingQuestion.PURPOSE and ctx.budget is not None:
                ctx.purpose = ctx.purpose or "nhu cầu sử dụng phổ thông"
            else:
                ctx.pending_question = clarification
                
                if clarification == PendingQuestion.BUDGET:
                    mode = "missing_budget"
                elif clarification == PendingQuestion.PURPOSE:
                    mode = "missing_purpose"
                else:
                    mode = "missing_budget"

                reply = await write_build_response(
                    mode=mode,
                    facts={"missing_info": clarification},
                    candidates=[],
                    user_message=user_message,
                )
                
                return self._early_reply(
                    reply,
                    ctx,
                    original_ctx,
                    clarification,
                )

        constraints = BuildConstraints(
            required_components=ctx.required_components,
            preferred_components=ctx.preferred_components,
            excluded_brands=ctx.excluded_brands,
        )

        unit_budget = get_unit_budget(ctx)

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
            return await self._build_not_found_reply(constraints, ctx, original_ctx, user_message)

        candidates = candidates[:5]

        decision = await choose_build(
            {
                "purpose": ctx.purpose,
                "budget": unit_budget,
                "quantity": ctx.quantity,
                "constraints": constraints.model_dump(mode="json"),
                "force_select": True,
            },
            candidates,
        )

        if decision.action != "select":
            logger.warning(
                "unexpected_pc_build_decision",
                extra={"action": decision.action},
            )

            selected = candidates[0]
            return await self._build_reply(
                selected,
                user_message,
                ctx,
                original_ctx,
            )

        selected = next((c for c in candidates if c.build_id == decision.selected_build_id), None)
        if not selected:
            selected = candidates[0]

        return await self._build_reply(
            selected,
            user_message,
            ctx,
            original_ctx,
        )
