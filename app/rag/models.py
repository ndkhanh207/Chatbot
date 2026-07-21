from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source_id: str
    source_type: Literal[
        "product",
        "build",
        "compatibility_report",
        "calculation",
    ]
    facts: dict[str, Any] = Field(default_factory=dict)


class EvidencePackage(BaseModel):
    query: str
    intent: str
    items: list[EvidenceItem] = Field(default_factory=list)
    insufficient: bool = False
    missing_information: list[str] = Field(default_factory=list)


class GroundedAnswerRequest(BaseModel):
    user_message: str
    intent: str
    evidence: EvidencePackage


class GroundedAnswer(BaseModel):
    answer: str
    used_source_ids: list[str] = Field(default_factory=list)
