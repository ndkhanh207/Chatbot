from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    COLLECTING = "collecting"
    CONFIGURED = "configured"
    SELECTED = "selected"


class ActiveTaskSummary(BaseModel):
    task_id: str
    domain: str
    status: TaskStatus
    pending_field: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
