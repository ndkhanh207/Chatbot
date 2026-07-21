from __future__ import annotations
from typing import Protocol

from app.chat.models import DomainRequest, ChatResult
from app.routing.models import RouteDecision
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent


class DomainHandler(Protocol):
    async def handle(
        self,
        request: DomainRequest,
        intent: ParsedIntent,
        route_decision: RouteDecision | None = None,
    ) -> ChatResult:
        ...
