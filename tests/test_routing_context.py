import asyncio
from unittest.mock import AsyncMock, Mock

from langchain_core.messages import AIMessage, HumanMessage

from app.memory.context_manager import recent_routing_turns, recent_user_messages
from app.pc_builder.extractor import build_extraction_messages
from app.pc_builder.models import PcBuildContext
from app.routing.models import (
    ContextRewrite,
    HandlerDescriptor,
    RouteDecision,
    RoutingRequest,
    TaskRelation,
)
from app.routing.planner import RoutePlanner, validate_route_decision
from app.tasks.models import ActiveTaskSummary, TaskStatus


def test_recent_user_messages_excludes_generated_build_reply():
    messages = [
        HumanMessage(content="build pc 30 triệu chơi game"),
        AIMessage(content="BUILD-03304, RTX 4070, giá 29.890.114 VNĐ"),
        HumanMessage(content="đổi GPU mạnh hơn"),
    ]

    selected = recent_user_messages(messages)

    assert [message.content for message in selected] == [
        "build pc 30 triệu chơi game",
        "đổi GPU mạnh hơn",
    ]


def test_routing_history_keeps_handler_label_but_excludes_assistant_reply():
    messages = [
        HumanMessage(content="RTX 5070 Ti VRAM bao nhiêu?"),
        AIMessage(
            content="Generated product facts and price",
            additional_kwargs={"intent": "specification"},
        ),
        HumanMessage(content="vậy RTX 5080 thì sao?"),
    ]

    selected = recent_routing_turns(messages)

    assert selected == [
        "user [previous_handler=specification]: RTX 5070 Ti VRAM bao nhiêu?",
        "user: vậy RTX 5080 thì sao?",
    ]
    assert all("Generated product facts" not in turn for turn in selected)


def test_extractor_prompt_excludes_generated_build_reply():
    messages = build_extraction_messages(
        user_message="đổi GPU mạnh hơn",
        recent_history=[
            HumanMessage(content="build pc 30 triệu chơi game"),
            AIMessage(content="BUILD-03304, RTX 4070, giá 29.890.114 VNĐ"),
        ],
        current_context=PcBuildContext(),
        route_decision=RouteDecision(
            handler_name="build_pc",
            rewritten_query="đổi GPU của bộ PC hiện tại",
            task_relation=TaskRelation.MODIFY_TASK,
            active_task_id="pc-build",
        ),
    )

    prompt = messages[-1]["content"]
    assert "user: build pc 30 triệu chơi game" in prompt
    assert "BUILD-03304" not in prompt
    assert "29.890.114" not in prompt
    assert "rewritten_query" not in prompt


def test_related_route_owns_sole_matching_active_task():
    decision = validate_route_decision(
        RouteDecision(
            handler_name="build_pc",
            rewritten_query="đổi GPU mạnh hơn",
            task_relation=TaskRelation.MODIFY_TASK,
        ),
        candidates=(
            HandlerDescriptor(
                name="build_pc",
                description="Build a PC",
                supported_operations=("update",),
                stateful=True,
            ),
        ),
        active_tasks=(
            ActiveTaskSummary(
                task_id="pc-build",
                domain="build_pc",
                status=TaskStatus.SELECTED,
            ),
        ),
    )

    assert decision.active_task_id == "pc-build"


def test_related_route_repairs_invented_handler_from_sole_active_task():
    decision = validate_route_decision(
        RouteDecision(
            handler_name="recommend",
            rewritten_query="cho mình xem bộ khác",
            task_relation=TaskRelation.CONTINUE_TASK,
        ),
        candidates=(
            HandlerDescriptor(
                name="build_pc",
                description="Build a PC",
                supported_operations=("alternative",),
                stateful=True,
            ),
        ),
        active_tasks=(
            ActiveTaskSummary(
                task_id="pc-build",
                domain="build_pc",
                status=TaskStatus.SELECTED,
            ),
        ),
    )

    assert decision.handler_name == "build_pc"
    assert decision.active_task_id == "pc-build"


def test_route_planner_retries_invalid_schema_without_history():
    model = AsyncMock()
    model.ainvoke.side_effect = [
        {
            "handler_name": "build_pc",
            "rewritten_query": "copied assistant reply",
        },
        {
            "handler_name": "build_pc",
            "rewritten_query": "đổi GPU của bộ PC hiện tại",
            "task_relation": "new_request",
            "active_task_id": None,
        },
    ]
    llm = Mock()
    rewrite_model = Mock()
    rewrite_model.ainvoke = AsyncMock(
        return_value=ContextRewrite(
            rewritten_query="đổi GPU của bộ PC hiện tại mạnh hơn",
            operation_changed=True,
        )
    )
    llm.with_structured_output.side_effect = lambda schema: (
        rewrite_model if schema is ContextRewrite else model
    )
    planner = RoutePlanner(llm=llm)
    request = RoutingRequest(
        user_message="đổi GPU mạnh hơn",
        recent_history=("user: build pc 30 triệu chơi game",),
        active_tasks=(),
    )
    candidates = (
        HandlerDescriptor(
            name="build_pc",
            description="Build a PC",
            supported_operations=("recommend",),
            stateful=True,
        ),
    )

    result = asyncio.run(planner.plan(request=request, candidates=candidates))

    assert result.ok
    assert result.value is not None
    assert result.value.handler_name == "build_pc"
    assert model.ainvoke.await_count == 2
    first_messages = model.ainvoke.await_args_list[0].args[0]
    retry_messages = model.ainvoke.await_args_list[1].args[0]
    assert any(
        "user: build pc 30 triệu chơi game" in message.content
        for message in first_messages
    )
    assert "Lịch sử:\nNone" in retry_messages[-2].content


def test_route_planner_repairs_invalid_handler_without_history():
    model = AsyncMock()
    model.ainvoke.side_effect = [
        {
            "handler_name": "recommend",
            "rewritten_query": "check these parts",
            "task_relation": "new_request",
            "active_task_id": None,
        },
        {
            "handler_name": "compatibility",
            "rewritten_query": "check these parts",
            "task_relation": "new_request",
            "active_task_id": None,
        },
    ]
    llm = Mock()
    llm.with_structured_output.return_value = model
    planner = RoutePlanner(llm=llm)
    request = RoutingRequest(
        user_message="check these parts",
        recent_history=(),
        active_tasks=(),
    )
    candidates = (
        HandlerDescriptor(
            name="compatibility",
            description="Check components",
            supported_operations=("check",),
            stateful=False,
        ),
    )

    result = asyncio.run(planner.plan(request=request, candidates=candidates))

    assert result.ok
    assert result.value.handler_name == "compatibility"
    assert model.ainvoke.await_count == 2
    correction = model.ainvoke.await_args_list[1].args[0][-1].content
    assert "exactly one of: compatibility" in correction


def test_route_planner_keeps_previous_stateless_handler_for_continuation():
    route_model = Mock()
    route_model.ainvoke = AsyncMock(
        return_value=RouteDecision(
            handler_name="price",
            rewritten_query="giá RTX 5080",
            task_relation=TaskRelation.NEW_REQUEST,
        )
    )
    rewrite_model = Mock()
    rewrite_model.ainvoke = AsyncMock(
        return_value=ContextRewrite(
            rewritten_query="xung nhịp của RTX 5080",
            operation_changed=False,
        )
    )
    llm = Mock()
    llm.with_structured_output.side_effect = lambda schema: (
        rewrite_model if schema is ContextRewrite else route_model
    )
    planner = RoutePlanner(llm=llm)
    request = RoutingRequest(
        user_message="vậy của RTX 5080 thì sao?",
        recent_history=(
            "user [previous_handler=specification]: thế còn xung nhịp?",
        ),
        active_tasks=(),
        previous_handler="specification",
    )
    candidates = (
        HandlerDescriptor(
            name="price",
            description="Prices",
            supported_operations=("price",),
            stateful=False,
        ),
        HandlerDescriptor(
            name="specification",
            description="Specifications",
            supported_operations=("spec",),
            stateful=False,
        ),
    )

    result = asyncio.run(planner.plan(request=request, candidates=candidates))

    assert result.ok
    assert result.value.handler_name == "specification"
    assert result.value.rewritten_query == "xung nhịp của RTX 5080"
    route_model.ainvoke.assert_awaited_once()
