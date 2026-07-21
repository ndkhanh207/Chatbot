from __future__ import annotations

import json
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from app.routing.models import RouteDecision, RoutingRequest, HandlerDescriptor
from app.routing.prompts import ROUTING_PROMPT
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

    if decision.handler_name not in allowed_handlers:
        raise InvalidRouteDecision(f"Selected handler {decision.handler_name!r} was not a candidate")

    if decision.active_task_id is not None:
        allowed_task_ids = {task.task_id for task in active_tasks}
        if decision.active_task_id not in allowed_task_ids:
            raise InvalidRouteDecision(f"Selected task {decision.active_task_id!r} does not exist")

    return decision


class RoutePlanner:
    def __init__(self, llm: ChatOllama) -> None:
        self._model = llm.with_structured_output(RouteDecision)

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
        
        prompt = ChatPromptTemplate.from_template(ROUTING_PROMPT)
        messages = prompt.format_messages(
            candidates_json=candidates_json,
            active_tasks_json=active_tasks_json,
            history="\n".join(request.recent_history) if request.recent_history else "None",
            user_message=request.user_message
        )

        async def _run() -> RouteDecision:
            decision: RouteDecision = await self._model.ainvoke(messages)
            return validate_route_decision(
                decision,
                candidates=candidates,
                active_tasks=request.active_tasks,
            )

        return await safe_llm_call(
            _run,
            timeout_seconds=15.0,
            max_attempts=2,
            operation_name="route_planner",
        )
