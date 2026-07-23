from __future__ import annotations
from typing import Protocol

from app.chat.models import DomainRequest, ChatResult
from app.routing.models import RouteDecision
from app.core.extraction.extractor import ExtractedEntities


class DomainHandler(Protocol):
    async def handle(
        self,
        request: DomainRequest,
        entities: ExtractedEntities,
        route_decision: RouteDecision | None = None,
    ) -> ChatResult:
        ...
