
import logging
from app.pc_builder.context import PcBuildContext, get_unit_budget
from app.pc_builder.reranker import write_build_response, choose_build
from app.pc_builder.extractor import extract_explicit_build_id, interpret_build_turn_safe, answers_pending_question
from app.pc_builder.state_merge import apply_interpretation_delta
from app.pc_builder.clarification import (
    clear_satisfied_pending_question,
    evaluate_request_completeness,
)
from app.pc_builder.formatter import (
    format_build_context,
    format_chat_history,
    render_selected_build_reply,
    format_approx_million,
)
from app.pc_builder.policy import PcBuildPolicy, PendingQuestion, ResponseMode
from app.catalog.models import BuildQuery, BuildConstraints
from app.chat.models import ChatResult
from app.pc_builder.models import PcBuildOutcome
from app.catalog import BuildRecord, ShopCatalog

logger = logging.getLogger(__name__)

class PcBuildService:
    def __init__(
        self,
        *,
        user_message: str,
        chat_history: list,
        current_context: PcBuildContext,
        catalog: ShopCatalog,
    ) -> None:
        self.user_message = user_message
        self.chat_history = chat_history
        self._current_context = current_context.model_copy(deep=True)
        self.ctx = current_context.model_copy(deep=True)
        self.catalog = catalog
        self.policy = PcBuildPolicy()

    def _outcome(self, reply: str, contexts: list[str] | None = None, handled: bool = True) -> PcBuildOutcome:
        result = ChatResult(
            reply=reply, 
            contexts=contexts or [], 
            handled=handled,
            metadata={'intent': 'build_pc'}
        )
        if not handled:
            self.ctx = self._current_context
            
        state_changed = (
            self.ctx.model_dump(mode='json') != self._current_context.model_dump(mode='json')
        )
        return PcBuildOutcome(
            result=result,
            next_context=self.ctx.model_copy(deep=True),
            state_changed=state_changed,
        )

    async def execute(self) -> PcBuildOutcome:
        explicit_build_id = extract_explicit_build_id(self.user_message)
        if explicit_build_id:
            return await self._handle_explicit_build(explicit_build_id)

        history_text = format_chat_history(
            self.chat_history,
            limit=self.policy.history_message_limit,
        )

        trusted_snapshot = self.ctx.model_dump(
            mode="json",
            exclude_none=True,
        )

        forced_route = None
        if answers_pending_question(self.user_message, self.ctx.pending_question):
            forced_route = "pc_builder"

        interpretation = await interpret_build_turn_safe(
            user_message=self.user_message,
            chat_history=history_text,
            trusted_snapshot=trusted_snapshot,
            forced_route=forced_route,
        )

        if not interpretation.ok or interpretation.value is None:
            logger.warning(
                "pc_builder_interpretation_failed",
                extra={
                    "error_kind": (
                        interpretation.error.value
                        if interpretation.error
                        else "unknown"
                    ),
                    "attempts": interpretation.attempts,
                },
            )

            reply = (
                "Hệ thống đang xử lý chậm nên em chưa thể "
                "hiểu chắc yêu cầu vừa rồi. Bạn thử lại sau nhé."
            )

            return self._outcome(reply, [reply])

        delta = interpretation.value

        if delta.route == "pass":
            return self._outcome("", handled=False)

        if delta.route == "current_build_qa":
            return await self._answer_about_current_build()

        merge_result = await apply_interpretation_delta(
            current=self.ctx,
            delta=delta,
            catalog=self.catalog,
        )

        if merge_result.has_errors:
            return self._early_reply(
                merge_result.clarification_question
                or "Yêu cầu chưa rõ, bạn nói lại giúp em nhé?",
                PendingQuestion.CLARIFICATION,
            )

        self.ctx = merge_result.next_state

        clear_satisfied_pending_question(self.ctx)

        clarification = evaluate_request_completeness(self.ctx)

        if clarification is not None:
            if clarification == PendingQuestion.PURPOSE and self.ctx.budget is not None:
                # Conversational mode: proceed to search, but suggest a balanced build
                self.ctx.purpose = self.ctx.purpose or "nhu cầu sử dụng phổ thông"
            else:
                self.ctx.pending_question = clarification
                
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
                    user_message=self.user_message,
                )
                
                return self._early_reply(
                    reply,
                    clarification,
                )

        constraints = BuildConstraints(
            required_components=self.ctx.required_components,
            preferred_components=self.ctx.preferred_components,
            excluded_brands=self.ctx.excluded_brands,
        )

        unit_budget = get_unit_budget(self.ctx)

        # Check for absolute minimum budget threshold dynamically
        if unit_budget is not None:
            minimum_query = BuildQuery(
                text=self.ctx.purpose or self.user_message,
                budget=None,
                constraints=constraints,
                excluded_ids=set(),
                price_order="asc",
                limit=1,
            )
            minimum_candidates = self.catalog.search_builds(minimum_query)

        # Exclude previous build if action is alternative
        excluded_ids = set()
        if delta.action == "alternative" and self.ctx.build_id:
            excluded_ids.add(self.ctx.build_id)

        query = BuildQuery(
            text=self.ctx.purpose or self.user_message,
            budget=unit_budget,
            constraints=constraints,
            excluded_ids=excluded_ids,
            limit=self.policy.retrieval_limit,
        )

        candidates = self.catalog.search_builds(query)

        if not candidates:
            return await self._build_not_found_reply(constraints)

        # Giới hạn số lượng candidates để tránh vượt quá context limit của LLM (4096 tokens)
        candidates = candidates[:5]

        decision = await choose_build(
            {
                "purpose": self.ctx.purpose,
                "budget": unit_budget,
                "quantity": self.ctx.quantity,
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
            print(f"DEBUG: choose_build returned action={decision.action}, response={decision.response_text}")

            selected = candidates[0]
            return await self._build_reply(
                selected,
                explanation=None,
            )
            
        print(f"DEBUG: choose_build returned select! id={decision.selected_build_id}")

        candidate_map = {
            candidate.build_id.casefold(): candidate
            for candidate in candidates
        }

        selected = candidate_map.get(
            (decision.selected_build_id or "").casefold(),
            candidates[0],
        )


        return await self._build_reply(
            selected,
            decision.recommendation_reason,
        )

    def _early_reply(self, reply: str, pending_question: PendingQuestion | None = None) -> PcBuildOutcome:
        self.ctx.pending_question = pending_question
        return self._outcome(reply, [reply])

    async def _build_not_found_reply(self, constraints: BuildConstraints) -> PcBuildOutcome:
        pending_question = None
        facts: dict = {}
        if self.ctx.budget is not None:
            facts["budget"] = format_approx_million(self.ctx.budget)
        if constraints.required_components:
            facts["components"] = dict(constraints.required_components)
            pending_question = PendingQuestion.DROP_CONSTRAINT
            
        reply = await write_build_response(
            mode="unavailable", 
            facts=facts, 
            candidates=[], 
            user_message=self.user_message
        )
        return self._early_reply(reply, pending_question=pending_question)

    async def _build_reply(
        self, 
        selected_record: BuildRecord, 
        explanation: str | None,
    ) -> PcBuildOutcome:
        build_id = selected_record.build_id
        
        canonical_block = format_build_context(selected_record)
        final_reply = render_selected_build_reply(
            canonical_block=canonical_block,
            explanation=explanation,
        )
        
        self.ctx.build_id = build_id
        self.ctx.pending_question = None
        
        return self._outcome(final_reply, [canonical_block])

    async def _answer_about_current_build(self) -> PcBuildOutcome:
        if not self.ctx.build_id:
            reply = await write_build_response(
                mode="missing_build", 
                facts={}, 
                candidates=[], 
                user_message=self.user_message
            )
            return self._outcome(reply, [reply])

        record = self.catalog.get_build(self.ctx.build_id)
        if not record:
            reply = await write_build_response(
                mode="missing_build", 
                facts={}, 
                candidates=[], 
                user_message=self.user_message
            )
            return self._outcome(reply, [reply])

        build_context = format_build_context(record)

        reply = await write_build_response(
            mode=ResponseMode.BUILD_QA, 
            facts={"context": build_context, "question": self.user_message},
            candidates=[record],
            user_message=self.user_message
        )
        return self._outcome(reply, [build_context])

    async def _handle_explicit_build(
        self,
        explicit_build_id: str,
    ) -> PcBuildOutcome:
        record = self.catalog.get_build(
            explicit_build_id
        )

        if record:
            self.ctx.build_id = record.build_id
            return await self._answer_about_specific_build(
                record
            )
        
        reply = await write_build_response(
            mode=ResponseMode.MISSING_BUILD, 
            facts={"build_id": explicit_build_id}
        )
        return self._outcome(reply, [reply])

    async def _answer_about_specific_build(self, build) -> PcBuildOutcome:
        build_context = format_build_context(build)
        reply = await write_build_response(
            mode=ResponseMode.BUILD_QA, 
            facts={"context": build_context, "question": self.user_message},
            candidates=[build],
            user_message=self.user_message
        )
        return self._outcome(reply, [build_context])


