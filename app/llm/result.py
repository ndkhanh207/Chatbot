from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar


T = TypeVar("T")


class LlmErrorKind(str, Enum):
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    SERVER_ERROR = "server_error"
    RATE_LIMIT = "rate_limit"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class LlmResult(Generic[T]):
    value: T | None = None
    error: LlmErrorKind | None = None
    message: str | None = None
    attempts: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None and self.value is not None