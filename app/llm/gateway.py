from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.llm.result import LlmErrorKind, LlmResult


logger = logging.getLogger(__name__)

T = TypeVar("T")


def _classify_exception(error: Exception) -> LlmErrorKind:
    name = type(error).__name__.casefold()
    message = str(error).casefold()

    if isinstance(error, asyncio.TimeoutError) or "timeout" in name:
        return LlmErrorKind.TIMEOUT

    if any(
        token in name or token in message
        for token in (
            "connection",
            "connecterror",
            "connection refused",
            "network",
        )
    ):
        return LlmErrorKind.CONNECTION

    if any(
        token in message
        for token in (
            "429",
            "rate limit",
            "too many requests",
        )
    ):
        return LlmErrorKind.RATE_LIMIT

    if any(
        token in message
        for token in (
            "500",
            "502",
            "503",
            "504",
            "internal server error",
            "bad gateway",
            "service unavailable",
        )
    ):
        return LlmErrorKind.SERVER_ERROR

    if any(
        token in name
        for token in (
            "validationerror",
            "jsondecodeerror",
            "outputparser",
        )
    ):
        return LlmErrorKind.INVALID_RESPONSE

    return LlmErrorKind.UNKNOWN


def _is_retryable(kind: LlmErrorKind) -> bool:
    return kind in {
        LlmErrorKind.TIMEOUT,
        LlmErrorKind.CONNECTION,
        LlmErrorKind.SERVER_ERROR,
        LlmErrorKind.RATE_LIMIT,
    }


async def safe_llm_call(
    operation: Callable[[], Awaitable[T]],
    *,
    timeout_seconds: float = 15,
    max_attempts: int = 2,
    operation_name: str = "llm_call",
) -> LlmResult[T]:
    last_error: Exception | None = None
    last_kind = LlmErrorKind.UNKNOWN

    for attempt in range(1, max_attempts + 1):
        try:
            value = await asyncio.wait_for(
                operation(),
                timeout=timeout_seconds,
            )

            return LlmResult(
                value=value,
                attempts=attempt,
            )

        except asyncio.CancelledError:
            # Never swallow application shutdown or request cancellation.
            raise

        except Exception as error:
            last_error = error
            last_kind = _classify_exception(error)

            logger.warning(
                "LLM operation failed",
                extra={
                    "operation": operation_name,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_kind": last_kind.value,
                    "error_type": type(error).__name__,
                },
                exc_info=error,
            )

            if (
                attempt >= max_attempts
                or not _is_retryable(last_kind)
            ):
                break

            # Exponential backoff with jitter.
            delay = min(
                0.5 * (2 ** (attempt - 1))
                + random.uniform(0, 0.25),
                3.0,
            )

            await asyncio.sleep(delay)

    return LlmResult(
        error=last_kind,
        message=(
            str(last_error)
            if last_error
            else "Unknown LLM failure"
        ),
        attempts=max_attempts,
    )
