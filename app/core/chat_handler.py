import traceback
import logging
from app.guard.input_guard import run_input_guards, check_semantic_guards
from app.memory.context_manager import ConversationContext
from app.chat.models import DomainRequest
from app.chat.registry import create_handler_registry
from app.pc_builder.repository import PcContextRepositoryImpl
from app.routing.planner import RoutePlanner
from app.routing.capability_index import AllCapabilitiesIndex
from app.routing.models import RoutingRequest
from app.tasks.registry import TaskRegistry, PcBuildTaskSummaryProvider
from app.core.llm_chains import get_llm

logger = logging.getLogger(__name__)

async def handle_chat(user_message: str, catalog, user_uid: str, session_id: str = "default") -> dict:
    memory = ConversationContext(user_uid, session_id)
    pc_repo = PcContextRepositoryImpl()

    if catalog is None:
        return {"chatbot_reply": "HỆ THỐNG CHƯA SẴN SÀNG!"}

    # 1. Security/input validation
    error_reply, user_message = run_input_guards(user_message, session_id)
    if error_reply:
        memory.commit(user_message, error_reply["chatbot_reply"], {"intent": "none"})
        return error_reply

    msg_clean = user_message.strip()
    chat_history = memory.history()

    # 2. Semantic shortcut/off-topic guard
    semantic_reply = check_semantic_guards(msg_clean, chat_history)
    if semantic_reply:
        memory.commit(msg_clean, semantic_reply["chatbot_reply"], {"intent": "none"})
        return semantic_reply

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
            recent_history=tuple(
                str(msg.content) if hasattr(msg, "content") else str(msg)
                for msg in chat_history[-6:]
            ),
            active_tasks=active_tasks,
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
            reply = "Hệ thống đang xử lý chậm nên chưa thể xác định yêu cầu của bạn. Bạn thử lại sau một chút nhé."
            memory.commit(
                msg_clean,
                reply,
                {"intent": "unavailable", "error_kind": error_kind},
            )
            return {"chatbot_reply": reply}

        route_decision = planner_result.value

        # --- TEMPORARY SHIM FOR LEGACY HANDLERS ---
        from app.core.intent.service import IntentService
        from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent

        if route_decision.handler_name != "build_pc":
            intent_service = IntentService()
            intent_result = await intent_service.parse(message=msg_clean, history=chat_history)
            parsed_intent = intent_result.value or ParsedIntent(intent="none")
        else:
            parsed_intent = ParsedIntent(intent="build_pc")
        # -------------------------------------------

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
            intent=parsed_intent,
            route_decision=route_decision,
        )

        # Fallback to general handler if unhandled
        if not chat_result.handled:
            general_handler = handler_registry.get_handler("general_chat")
            chat_result = await general_handler.handle(
                request=domain_req,
                intent=ParsedIntent(intent="none"),
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

    except Exception as e:
        traceback.print_exc()
        print(f"❌ [INTERNAL ERROR - chat_handler] Lỗi xử lý: {str(e)}")
        raise
