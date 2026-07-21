from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PendingQuestion(str, Enum):
    GENERAL = "general"
    BUDGET = "budget"
    PURPOSE = "purpose"
    BUDGET_SCOPE = "budget_scope"
    CLARIFICATION = "clarification"
    DROP_CONSTRAINT = "drop_constraint"


class ResponseMode(str, Enum):
    BUDGET_GAP = "budget_gap"
    UNAVAILABLE = "unavailable"
    MISSING_BUILD = "missing_build"
    INVALID_BUDGET = "invalid_budget"
    MISSING_BUDGET = "missing_budget"
    MISSING_PURPOSE = "missing_purpose"
    BUILD_QA = "build_qa"


@dataclass(frozen=True, slots=True)
class PcBuildPolicy:
    history_message_limit: int = 6
    retrieval_limit: int = 10
