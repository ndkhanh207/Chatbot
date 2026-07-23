from __future__ import annotations

import json
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import ValidationError

from app.routing.models import (
    ContextRewrite,
    HandlerDescriptor,
    RouteDecision,
    RoutingRequest,
    TaskRelation,
)
from app.routing.prompts import ROUTING_EXAMPLES, ROUTING_PROMPT
from app.llm.gateway import safe_llm_call, LlmResult


class InvalidRouteDecision(Exception):
    pass


def validate_route_decision(
    decision: RouteDecision,
    *,
    candidates: tuple[HandlerDescriptor, ...],
    active_tasks: tuple,
) -> RouteDecision:
    allowed_handlers = {candidate.name for candidate in candidates}
    tasks_by_id = {task.task_id: task for task in active_tasks}

    if decision.active_task_id is not None:
        task = tasks_by_id.get(decision.active_task_id)
        if task is None:
            raise InvalidRouteDecision(f"Selected task {decision.active_task_id!r} does not exist")
        if decision.task_relation != TaskRelation.NEW_REQUEST:
            decision = decision.model_copy(update={"handler_name": task.domain})

    if (
        decision.task_relation != TaskRelation.NEW_REQUEST
        and decision.active_task_id is None
    ):
        matching_tasks = [task for task in active_tasks if task.domain == decision.handler_name]
        if not matching_tasks and len(active_tasks) == 1:
            matching_tasks = [active_tasks[0]]
        if len(matching_tasks) == 1:
            task = matching_tasks[0]
            decision = decision.model_copy(update={
                "handler_name": task.domain,
                "active_task_id": task.task_id,
            })
        else:
            decision = decision.model_copy(update={"task_relation": TaskRelation.NEW_REQUEST})

    # Force route if there is an active task with a pending field and the decision is a new request
    if decision.task_relation == TaskRelation.NEW_REQUEST and len(active_tasks) == 1:
        task = active_tasks[0]
        if task.pending_field:
            decision = decision.model_copy(update={
                "handler_name": task.domain,
                "task_relation": TaskRelation.CONTINUE_TASK,
                "active_task_id": task.task_id,
            })

    if decision.handler_name not in allowed_handlers:
        raise InvalidRouteDecision(f"Selected handler {decision.handler_name!r} was not a candidate")

    return decision


class RoutePlanner:
    def __init__(self, llm: ChatOllama) -> None:
        self._llm = llm
        self._model = llm.with_structured_output(RouteDecision)

    async def _rewrite_with_history(self, request: RoutingRequest) -> ContextRewrite:
        if not request.recent_history:
            return ContextRewrite(
                rewritten_query=request.user_message,
                operation_changed=True,
            )
        rewrite_model = self._llm.with_structured_output(ContextRewrite)
        response = await rewrite_model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Rewrite the current Vietnamese message as one standalone request "
                        "using only the prior user turns. Preserve the latest requested "
                        "operation, technical attribute, constraints, and product context. "
                        "Set operation_changed=false when the current message is an elliptical "
                        "continuation of the previous operation. Set it true only when the user "
                        "explicitly requests a different operation. Do not answer or classify."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Prior user turns:\n{'\n'.join(request.recent_history)}\n"
                        f"Current message: {request.user_message}"
                    )
                ),
            ]
        )
        return (
            response
            if isinstance(response, ContextRewrite)
            else ContextRewrite.model_validate(response)
        )

    async def plan(
        self,
        request: RoutingRequest,
        candidates: tuple[HandlerDescriptor, ...],
    ) -> LlmResult[RouteDecision]:
        
        candidates_json = json.dumps(
            [c.model_dump() for c in candidates],
            ensure_ascii=False,
            indent=2
        )
        active_tasks_json = json.dumps(
            [t.model_dump() for t in request.active_tasks],
            ensure_ascii=False,
            indent=2
        )
        
        prompt = ChatPromptTemplate.from_messages([("system", ROUTING_PROMPT)])
        async def _invoke(
            history: tuple[str, ...],
            route_message: str,
            correction: str | None = None,
        ) -> RouteDecision:
            messages = prompt.format_messages(
                candidates_json=candidates_json,
                active_tasks_json=active_tasks_json,
            )
            for example_input, example_output in ROUTING_EXAMPLES:
                messages.extend(
                    (
                        HumanMessage(content=example_input),
                        AIMessage(content=json.dumps(example_output, ensure_ascii=False)),
                    )
                )
            messages.append(
                HumanMessage(
                    content=(
                        f"Lịch sử:\n{'\n'.join(history) if history else 'None'}\n"
                        f"Tin nhắn hiện tại: {route_message}"
                    )
                )
            )
            if correction:
                messages.append(HumanMessage(content=correction))
            result = await self._model.ainvoke(messages)
            decision = (
                result
                if isinstance(result, RouteDecision)
                else RouteDecision.model_validate(result)
            )
            return validate_route_decision(
                decision,
                candidates=candidates,
                active_tasks=request.active_tasks,
            )

        async def _run() -> RouteDecision:
            rewrite = await self._rewrite_with_history(request)
            route_message = rewrite.rewritten_query
            previous = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.name == request.previous_handler
                ),
                None,
            )
            try:
                decision = await _invoke(request.recent_history, route_message)
            except (OutputParserException, ValidationError, InvalidRouteDecision) as error:
                allowed = ", ".join(sorted(c.name for c in candidates))
                decision = await _invoke(
                    (),
                    route_message,
                    correction=(
                        f"Previous output was invalid: {error}. "
                        f"Set handler_name to exactly one of: {allowed}. "
                        "Return corrected structured output only."
                    ),
                )
            selected = next(
                candidate for candidate in candidates
                if candidate.name == decision.handler_name
            )
            if (
                previous is not None
                and not previous.stateful
                and not selected.stateful
                and not rewrite.operation_changed
            ):
                return decision.model_copy(
                    update={
                        "handler_name": previous.name,
                        "rewritten_query": route_message,
                    }
                )
            return decision

        return await safe_llm_call(
            _run,
            timeout_seconds=30.0,
            max_attempts=2,
            operation_name="route_planner",
        )
