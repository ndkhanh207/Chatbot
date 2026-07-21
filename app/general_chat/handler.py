from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.rag.models import EvidencePackage, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer

class GeneralChatHandler:
    async def handle(self, request: DomainRequest, intent: ParsedIntent, route_decision=None) -> ChatResult:
        evidence = EvidencePackage(
            query=request.user_message,
            intent=intent.intent,
            items=[]
        )
        generation = await generate_grounded_answer(
            GroundedAnswerRequest(
                user_message=request.user_message,
                intent=intent.intent,
                evidence=evidence,
                chat_history=request.chat_history
            )
        )
        
        if generation.ok and generation.value:
            reply = generation.value.answer
        else:
            from app.responses import response_renderer, ResponseCode
            reply = response_renderer.render(ResponseCode.LLM_UNAVAILABLE)
            

        return ChatResult(
            reply=reply,
            contexts=[],
            metadata={"intent": intent.intent}
        )
