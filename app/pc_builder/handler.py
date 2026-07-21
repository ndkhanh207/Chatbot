import logging
from app.chat.models import DomainRequest, ChatResult
from app.routing.models import RouteDecision
from app.pc_builder.service import PcBuildService
from app.pc_builder.context import PcBuildContext
from app.pc_builder.models import PcBuildOutcome, PcContextRepository
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.pc_builder.extractor import extract_pc_build_command
from app.catalog import ShopCatalog

logger = logging.getLogger(__name__)

class PCBuilderHandler:
    def __init__(
        self,
        *,
        catalog: ShopCatalog,
        repository: PcContextRepository,
    ) -> None:
        self._catalog = catalog
        self._repository = repository

    async def handle(
        self,
        request: DomainRequest,
        intent: ParsedIntent,
        route_decision: RouteDecision | None = None,
    ) -> ChatResult:
        versioned_ctx = await self._repository.load(request.user_uid, request.session_id)
        current_context = versioned_ctx.context
        expected_version = versioned_ctx.version
        
        if route_decision is None:
            from app.routing.models import RouteDecision, TaskRelation
            route_decision = RouteDecision(
                handler_name="build_pc",
                rewritten_query=request.user_message,
                task_relation=TaskRelation.CONTINUE_TASK
            )

        command_result = await extract_pc_build_command(
            user_message=request.user_message,
            recent_history=request.chat_history,
            current_context=current_context,
            route_decision=route_decision,
        )

        if not command_result.ok or command_result.value is None:
            logger.warning(
                "pc_builder_extraction_failed",
                extra={
                    "error_kind": (
                        command_result.error.value
                        if command_result.error
                        else "unknown"
                    ),
                    "attempts": command_result.attempts,
                },
            )
            return ChatResult(
                reply="Hệ thống đang xử lý chậm nên em chưa hiểu chắc yêu cầu vừa rồi. Bạn thử lại sau nhé.",
                contexts=[],
                handled=False,
            )

        command = command_result.value

        service = PcBuildService(
            catalog=self._catalog,
        )

        outcome: PcBuildOutcome = await service.execute(
            command=command,
            current_context=current_context,
            user_message=request.user_message,
        )

        if outcome.state_changed:
            await self._repository.save(
                user_uid=request.user_uid,
                session_id=request.session_id,
                context=outcome.next_context,
                expected_version=expected_version,
            )

        return outcome.result
