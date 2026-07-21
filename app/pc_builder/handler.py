from app.chat.models import DomainRequest
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.pc_builder.service import PcBuildService
from app.pc_builder.context import PcBuildContext
from app.pc_builder.models import PcBuildOutcome

class PCBuilderHandler:
    def __init__(
        self,
        *,
        catalog
    ) -> None:
        self._catalog = catalog

    async def handle_with_state(
        self,
        request: DomainRequest,
        intent: ParsedIntent,
        current_context: PcBuildContext,
    ) -> PcBuildOutcome:
        service = PcBuildService(
            user_message=request.user_message,
            chat_history=request.chat_history,
            current_context=current_context,
            catalog=self._catalog,
        )

        return await service.execute()
