from app.pc_builder.formatter import interpretation_failure_reply
import logging
from app.pc_builder.context import ConversationMemory, get_unit_budget
from app.pc_builder.reranker import write_build_response, choose_build, BuildSelectionError
from app.pc_builder.extractor import extract_explicit_build_id, interpret_build_turn, Interpretation, InterpretationError, answers_pending_question
from app.pc_builder.state_merge import apply_interpretation_delta
from app.pc_builder.clarification import (
    clear_satisfied_pending_question,
    evaluate_request_completeness,
)
from app.pc_builder.formatter import (
    format_build_context,
    format_chat_history,
    format_merge_conflict_error,
    render_selected_build_reply,
)
from app.pc_builder.policy import PcBuildPolicy, PendingQuestion, ResponseMode
from app.catalog.models import BuildQuery, BuildConstraints

logger = logging.getLogger(__name__)

class PcBuildEngine:
    def __init__(self, user_uid: str, session_id: str, user_message: str, user_message_fixed: str, msg_lower: str, search_query: str, chat_history: list, catalog, is_build_pc: bool):
        self.user_uid = user_uid
        self.session_id = session_id
        self.user_message = user_message
        self.user_message_fixed = user_message_fixed
        self.msg_lower = msg_lower
        self.search_query = search_query
        self.chat_history = chat_history
        self.catalog = catalog
        self.is_build_pc = is_build_pc
        
        self.memory = ConversationMemory(user_uid, session_id)
        self.ctx = self.memory.load_context()
        self.policy = PcBuildPolicy()

    @staticmethod
    def _result(reply: str, contexts: list[str] | None = None) -> dict:
        return {'chatbot_reply': reply, 'contexts': contexts or []}

    def _has_active_session(self) -> bool:
        return bool(self.ctx.build_id or self.ctx.purpose or self.ctx.budget or self.ctx.required_components)

    async def execute(self) -> dict | None:
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

        try:
            delta = await interpret_build_turn(
                user_message=self.user_message,
                chat_history=history_text,
                trusted_snapshot=trusted_snapshot,
                forced_route=forced_route,
            )
        except InterpretationError as error:
            logger.warning(
                "PC build interpretation failed",
                exc_info=error,
            )
            reply = interpretation_failure_reply(self.ctx)
            self.memory.commit_turn(
                self.user_message,
                reply,
                self.ctx,
            )
            return self._result(reply, [reply])

        if delta.route == "pass":
            return None

        if delta.route == "current_build_qa":
            return await self._answer_about_current_build()

        merge_result = apply_interpretation_delta(
            current=self.ctx,
            delta=delta,
            catalog=self.catalog,
        )

        if merge_result.has_errors:
            return self._commit_early_reply(
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
                
                return self._commit_early_reply(
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
            if minimum_candidates and unit_budget < minimum_candidates[0].total_price:
                reply = await write_build_response(
                    "invalid_budget", 
                    {"budget": unit_budget, "min_price": minimum_candidates[0].total_price}, 
                    [], 
                    self.user_message
                )
                return self._commit_early_reply(reply, pending_question=PendingQuestion.BUDGET)

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
            },
            candidates,
        )

        if decision.action == "clarify":
            return self._commit_early_reply(
                decision.clarification_question or "",
                PendingQuestion.CLARIFICATION,
            )

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

    def _commit_early_reply(self, reply: str, pending_question: PendingQuestion | None = None) -> dict:
        self.ctx.pending_question = pending_question
        self.memory.commit_turn(self.user_message, reply, self.ctx)
        return self._result(reply, [reply])

    async def _build_not_found_reply(self, constraints: BuildConstraints) -> dict:
        pending_question = None
        facts: dict = {"budget": self.ctx.budget}
        if constraints.required_components:
            facts["components"] = dict(constraints.required_components)
            pending_question = PendingQuestion.DROP_CONSTRAINT
            
        reply = await write_build_response(
            mode="unavailable", 
            facts=facts, 
            candidates=[], 
            user_message=self.user_message
        )
        return self._commit_early_reply(reply, pending_question=pending_question)

    async def _build_reply(self, selected_record, explanation: str | None) -> dict:
        best_build = selected_record.attributes
        build_id = selected_record.build_id
        
        canonical_block = format_build_context(selected_record)
        final_reply = render_selected_build_reply(
            canonical_block=canonical_block,
            explanation=explanation,
        )
        
        self.ctx.build_id = build_id
        self.ctx.pending_question = None
        

        self.memory.commit_turn(self.user_message, final_reply, self.ctx)
        return self._result(final_reply, [canonical_block])

    async def _answer_about_current_build(self) -> dict:
        if not self.ctx.build_id:
            reply = await write_build_response(
                mode="missing_build", 
                facts={}, 
                candidates=[], 
                user_message=self.user_message
            )
            self.memory.commit_turn(self.user_message, reply, self.ctx)
            return self._result(reply, [reply])

        build_context = ""
        record = self.catalog.get_build(self.ctx.build_id)
        if record:
            build_context = format_build_context(record)
                
        if not build_context:
            reply = await write_build_response(
                mode="missing_build", 
                facts={}, 
                candidates=[], 
                user_message=self.user_message
            )
            self.memory.commit_turn(self.user_message, reply, self.ctx)
            return self._result(reply, [reply])

        reply = await write_build_response(
            mode=ResponseMode.BUILD_QA, 
            facts={"context": build_context, "question": self.user_message},
            candidates=[record],
            user_message=self.user_message
        )
        self.memory.commit_turn(self.user_message, reply, self.ctx)
        return self._result(reply, [build_context])

    async def _handle_explicit_build(self, explicit_build_id: str) -> dict:
        record = self.catalog.get_build(explicit_build_id)
        if record:
            return await self._answer_about_specific_build(record)
        
        reply = await write_build_response(mode=ResponseMode.MISSING_BUILD, facts={"build_id": explicit_build_id})
        self.memory.commit_turn(self.user_message, reply, self.ctx)
        return self._result(reply, [reply])

    async def _answer_about_specific_build(self, build) -> dict:
        build_context = format_build_context(build)
        reply = await write_build_response(
            mode=ResponseMode.BUILD_QA, 
            facts={"context": build_context, "question": self.user_message},
            candidates=[build],
            user_message=self.user_message
        )
        self.memory.commit_turn(self.user_message, reply, self.ctx)
        return self._result(reply, [build_context])

async def handle_pc_build_flow(
    user_uid: str,
    session_id: str,
    user_message: str,
    user_message_fixed: str,
    msg_lower: str,
    search_query: str,
    chat_history: list,
    catalog,
    is_build_pc: bool,
) -> dict | None:
    engine = PcBuildEngine(
        user_uid, session_id, user_message, user_message_fixed, msg_lower,
        search_query, chat_history, catalog, is_build_pc
    )
    return await engine.execute()
