import traceback
from app.guard.input_guard import run_input_guards, check_semantic_guards
from app.memory.context_manager import ConversationContext
from app.pc_builder.extractor import answers_pending_question
from app.core.intent.service import IntentService
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.chat.models import DomainRequest
from app.chat.registry import create_handler_registry
from app.core.intent.history_context import build_intent_metadata
from app.pc_builder.repository import PcContextRepositoryImpl

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

    # 2. Load history and PC task state
    chat_history = memory.history()
    pc_versioned = await pc_repo.load(user_uid, session_id)
    pc_context = pc_versioned.context

    # 3. Pending-answer guard
    if pc_context.pending_question and answers_pending_question(msg_clean, pc_context.pending_question):
        parsed_intent = ParsedIntent(intent="build_pc")
    else:
        # 4. Semantic shortcut/off-topic guard
        semantic_reply = check_semantic_guards(msg_clean, chat_history)
        if semantic_reply:
            memory.commit(msg_clean, semantic_reply["chatbot_reply"], {"intent": "none"})
            return semantic_reply

        # 5. IntentService
        intent_service = IntentService()
        intent_result = await intent_service.parse(
            message=msg_clean,
            history=chat_history,
        )

        if not intent_result.ok:
            error_kind = intent_result.error if intent_result.error else "unknown"
            reply = "Hệ thống đang xử lý chậm nên chưa thể xác định yêu cầu của bạn. Bạn thử lại sau một chút nhé."
            memory.commit(
                msg_clean,
                reply,
                {"intent": "unavailable", "error_kind": error_kind},
            )
            return {"chatbot_reply": reply}

        parsed_intent = intent_result.value
        assert parsed_intent is not None
        
        # 5b. Active PC Builder Session Override
        if parsed_intent.intent in ("none", "budget_search", "price_check"):
            is_active_pc_session = bool(
                pc_context.budget
                or pc_context.purpose
                or pc_context.required_components
                or pc_context.build_id
            )
            if is_active_pc_session:
                parsed_intent = ParsedIntent(intent="build_pc")

    try:
        # 6. HandlerRegistry
        registry = create_handler_registry(catalog)
        domain_handler = registry.get(parsed_intent.intent)
        
        domain_req = DomainRequest(
            user_message=msg_clean,
            user_uid=user_uid,
            session_id=session_id,
            chat_history=chat_history
        )
        
        if parsed_intent.intent == "build_pc":
            outcome = await domain_handler.handle_with_state(  # type: ignore
                request=domain_req,
                intent=parsed_intent,
                current_context=pc_context
            )
            chat_result = outcome.result
            if outcome.state_changed:
                await pc_repo.save(
                    user_uid=user_uid,
                    session_id=session_id,
                    context=outcome.next_context,
                    expected_version=pc_versioned.version
                )
        else:
            chat_result = await domain_handler.handle(domain_req, parsed_intent)

        # Fallback to general handler if unhandled
        if not chat_result.handled:
            general_handler = registry.get("none")
            chat_result = await general_handler.handle(domain_req, ParsedIntent(intent="none"))

        # 7. Commit once
        meta = build_intent_metadata(parsed_intent)
        meta.update(chat_result.metadata)
        memory.commit(msg_clean, chat_result.reply, meta)
            
        return {
            "chatbot_reply": chat_result.reply,
            "contexts": chat_result.contexts
        }

    except Exception as e:
        traceback.print_exc()
        print(f"❌ [INTERNAL ERROR - chat_handler] Lỗi xử lý LLM: {str(e)}")
        raise
