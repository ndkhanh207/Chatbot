from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from app.tasks.models import ActiveTaskSummary


class HandlerDescriptor(BaseModel):
    name: str
    description: str
    supported_operations: tuple[str, ...]
    stateful: bool = False


class RoutingRequest(BaseModel):
    user_message: str
    recent_history: tuple[str, ...]
    active_tasks: tuple[ActiveTaskSummary, ...]
    previous_handler: str | None = None


class ContextRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rewritten_query: str = Field(min_length=1, max_length=1000)
    operation_changed: bool


class TaskRelation(str, Enum):
    NEW_REQUEST = "new_request"
    CONTINUE_TASK = "continue_task"
    MODIFY_TASK = "modify_task"
    TASK_QUESTION = "task_question"


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handler_name: str = Field(description="Tên của trình xử lý (handler) được chọn từ danh sách Candidates.")
    rewritten_query: str = Field(min_length=1, max_length=1000, description="Truy vấn được viết lại rõ ràng, đầy đủ ngữ cảnh độc lập.")
    task_relation: TaskRelation = Field(description="Mối quan hệ của yêu cầu này với các tác vụ đang hoạt động.")
    active_task_id: str | None = Field(default=None, description="ID của tác vụ đang hoạt động nếu có liên quan, ngược lại là null.")
