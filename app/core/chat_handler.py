import traceback
import logging
from app.guard.input_guard import run_input_guards
from app.memory.context_manager import (
    ConversationContext,
    latest_routing_handler,
    recent_routing_turns,
)
from app.chat.models import DomainRequest
from app.chat.registry import create_handler_registry
from app.infrastructure.pc_context_repository import SqlPcContextRepository
from app.routing.planner import RoutePlanner
from app.routing.capability_index import AllCapabilitiesIndex
from app.routing.models import RoutingRequest
from app.tasks.registry import TaskRegistry, PcBuildTaskSummaryProvider
from app.core.llm_chains import get_llm
from app.responses import ResponseCode, response_renderer, ResponseGenerationUnavailable, CatalogUnavailable

logger = logging.getLogger(__name__)

async def handle_chat(user_message: str, catalog, user_uid: str, session_id: str = "default") -> dict:
    memory = ConversationContext(user_uid, session_id)
    pc_repo = SqlPcContextRepository()

    if catalog is None:
        return {"chatbot_reply": "HỆ THỐNG CHƯA SẴN SÀNG!"}

    # 1. Security/input validation
    guard_decision, user_message = run_input_guards(user_message, session_id)
    if not guard_decision.allowed:
        rc = ResponseCode.UNSAFE_CONTENT
        if guard_decision.response_code is not None:
            mapping = {
                "message_too_long": ResponseCode.INPUT_TOO_LONG,
                "empty_input": ResponseCode.EMPTY_INPUT,
                "invalid_format": ResponseCode.INVALID_FORMAT,
                "unsafe_content": ResponseCode.UNSAFE_CONTENT,
            }
            rc = mapping.get(guard_decision.response_code.value, ResponseCode.UNSAFE_CONTENT)
            
        reply = response_renderer.render(rc)
        memory.commit(user_message, reply, {"intent": "none"})
        return {"chatbot_reply": reply, "contexts": []}

    msg_clean = user_message.strip()
    chat_history = memory.history()

    try:
        # 3. Setup Registries
        task_registry = TaskRegistry(providers=[
            PcBuildTaskSummaryProvider(repository=pc_repo)
        ])
        handler_registry = create_handler_registry(catalog=catalog, pc_repository=pc_repo)
        capability_index = AllCapabilitiesIndex(registry=handler_registry)

        # 4. Routing
        active_tasks = await task_registry.get_active_tasks(
            user_uid=user_uid,
            session_id=session_id
        )

        routing_request = RoutingRequest(
            user_message=msg_clean,
            recent_history=tuple(recent_routing_turns(chat_history)),
            active_tasks=active_tasks,
            previous_handler=latest_routing_handler(chat_history),
        )

        candidates = await capability_index.retrieve(routing_request)

        planner = RoutePlanner(llm=get_llm())
        planner_result = await planner.plan(
            request=routing_request,
            candidates=candidates,
        )

        if not planner_result.ok or planner_result.value is None:
            error_kind = planner_result.error.value if planner_result.error else "unknown"
            logger.warning(
                "route_planner_failed",
                extra={"error_kind": error_kind, "attempts": planner_result.attempts}
            )
            reply = response_renderer.render(ResponseCode.ROUTING_UNAVAILABLE)
            memory.commit(
                msg_clean,
                reply,
                {"intent": "unavailable", "error_kind": error_kind},
            )
            return {"chatbot_reply": reply}

        route_decision = planner_result.value

        from app.core.extraction.service import EntityExtractor
        from app.core.extraction.extractor import ExtractedEntities

        # Bước 2: Extract Entities (Stateless, based solely on rewritten query)
        extractor = EntityExtractor()
        entities_result = await extractor.extract_entities(
            message=route_decision.rewritten_query, 
            handler_name=route_decision.handler_name
        )
        
        parsed_entities = entities_result.value if entities_result.value else ExtractedEntities(intent=route_decision.handler_name)

        # 5. Dispatch
        domain_handler = handler_registry.get_handler(route_decision.handler_name)
        
        domain_req = DomainRequest(
            user_message=msg_clean,
            user_uid=user_uid,
            session_id=session_id,
            chat_history=chat_history
        )
        
        chat_result = await domain_handler.handle(
            request=domain_req,
            entities=parsed_entities,
            route_decision=route_decision,
        )

        # Fallback to general handler if unhandled
        if not chat_result.handled:
            general_handler = handler_registry.get_handler("general_chat")
            chat_result = await general_handler.handle(
                request=domain_req,
                entities=ExtractedEntities(intent="general_chat"),
                route_decision=route_decision,
            )

        # 6. Commit
        meta = {
            "intent": route_decision.handler_name,
            "task_relation": route_decision.task_relation.value,
            "active_task_id": route_decision.active_task_id,
        }
        meta.update(chat_result.metadata)
        memory.commit(msg_clean, chat_result.reply, meta)
            
        return {
            "chatbot_reply": chat_result.reply,
            "contexts": chat_result.contexts
        }

    except ResponseGenerationUnavailable:
        reply = response_renderer.render(ResponseCode.LLM_UNAVAILABLE)
        return {"chatbot_reply": reply, "contexts": []}
    except CatalogUnavailable:
        reply = response_renderer.render(ResponseCode.CATALOG_UNAVAILABLE)
        return {"chatbot_reply": reply, "contexts": []}
    except Exception as e:
        traceback.print_exc()
        print(f"❌ [INTERNAL ERROR - chat_handler] Lỗi xử lý: {str(e)}")
        reply = response_renderer.render(ResponseCode.SYSTEM_ERROR)
        return {"chatbot_reply": reply, "contexts": []}
