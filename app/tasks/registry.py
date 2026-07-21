from __future__ import annotations
import asyncio
from typing import Protocol

from app.tasks.models import ActiveTaskSummary, TaskStatus
from app.pc_builder.repository import PcContextRepository
from app.pc_builder.models import PcBuildStatus


class TaskSummaryProvider(Protocol):
    async def get_active_tasks(
        self,
        *,
        user_uid: str,
        session_id: str,
    ) -> list[ActiveTaskSummary]:
        ...


class PcBuildTaskSummaryProvider:
    def __init__(
        self,
        repository: PcContextRepository,
    ) -> None:
        self._repository = repository

    async def get_active_tasks(
        self,
        *,
        user_uid: str,
        session_id: str,
    ) -> list[ActiveTaskSummary]:
        versioned = await self._repository.load(
            user_uid=user_uid,
            session_id=session_id,
        )

        context = versioned.context

        if context.status == PcBuildStatus.IDLE:
            return []
            
        status_map = {
            PcBuildStatus.COLLECTING: TaskStatus.COLLECTING,
            PcBuildStatus.CONFIGURED: TaskStatus.CONFIGURED,
            PcBuildStatus.SELECTED: TaskStatus.SELECTED,
        }

        return [
            ActiveTaskSummary(
                task_id="pc-build",
                domain="build_pc",
                status=status_map[context.status],
                pending_field=(
                    context.pending_question.value
                    if context.pending_question
                    else None
                ),
                facts={
                    "budget": context.budget,
                    "purpose": context.purpose,
                    "build_id": context.build_id,
                    "required_components": context.required_components,
                },
            )
        ]


class TaskRegistry:
    def __init__(
        self,
        providers: list[TaskSummaryProvider],
    ) -> None:
        self._providers = tuple(providers)

    async def get_active_tasks(
        self,
        *,
        user_uid: str,
        session_id: str,
    ) -> tuple[ActiveTaskSummary, ...]:
        groups = await asyncio.gather(
            *[
                provider.get_active_tasks(
                    user_uid=user_uid,
                    session_id=session_id,
                )
                for provider in self._providers
            ]
        )

        return tuple(
            task
            for group in groups
            for task in group
        )
