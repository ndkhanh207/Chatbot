from __future__ import annotations

from typing import Protocol
from app.routing.models import HandlerDescriptor, RoutingRequest
from app.chat.registry import HandlerRegistry


class HandlerCapabilityIndex(Protocol):
    async def retrieve(
        self,
        request: RoutingRequest,
        *,
        limit: int | None = None,
    ) -> tuple[HandlerDescriptor, ...]:
        ...


class AllCapabilitiesIndex:
    def __init__(
        self,
        registry: HandlerRegistry,
    ) -> None:
        self._registry = registry

    async def retrieve(
        self,
        request: RoutingRequest,
        *,
        limit: int | None = None,
    ) -> tuple[HandlerDescriptor, ...]:
        descriptors = self._registry.descriptors()

        if limit is None:
            return descriptors

        return descriptors[:limit]
