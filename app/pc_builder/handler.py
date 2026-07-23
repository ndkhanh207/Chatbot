import logging
from app.chat.models import DomainRequest, ChatResult
from app.routing.models import RouteDecision
from app.pc_builder.service import PcBuildService
from app.pc_builder.models import PcBuildOutcome, PcContextRepository
from app.pc_builder.extractor import extract_pc_build_command
from app.core.extraction.extractor import ExtractedEntities
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

    def _extraction_failure(self) -> ChatResult:
        from app.responses import response_renderer, ResponseCode
        reply = response_renderer.render(ResponseCode.LLM_UNAVAILABLE)
        return ChatResult(
            reply=reply,
            contexts=[],
            handled=False,
        )

    async def handle(
        self,
        request: DomainRequest,
        entities: ExtractedEntities,
        route_decision: RouteDecision | None = None,
        **kwargs
    ) -> ChatResult:
        versioned = await self._repository.load(
            request.user_uid,
            request.session_id,
        )

        if route_decision is None:
            logger.error("route_decision is required for PC build extraction but was None")
            return self._extraction_failure()
        command_result = await extract_pc_build_command(
            user_message=request.user_message,
            recent_history=request.chat_history,
            current_context=versioned.context,
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
            return self._extraction_failure()

        service = PcBuildService(catalog=self._catalog)

        outcome: PcBuildOutcome = await service.execute(
            command=command_result.value,
            current_context=versioned.context,
            user_message=request.user_message,
        )

        if outcome.state_changed:
            await self._repository.save(
                user_uid=request.user_uid,
                session_id=request.session_id,
                context=outcome.next_context,
                expected_version=versioned.version,
            )

        return outcome.result
