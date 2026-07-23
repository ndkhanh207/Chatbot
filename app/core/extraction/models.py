from typing import Literal
from pydantic import BaseModel
from app.core.extraction.extractor import ExtractedEntities

LlmErrorKind = Literal[
    "timeout",
    "validation_error",
    "parsing_error",
    "unknown"
]

class ExtractionResult(BaseModel):
    value: ExtractedEntities | None = None
    error: LlmErrorKind | None = None
    source: Literal[
        "llm",
        "fallback",
    ]

    @property
    def ok(self) -> bool:
        return self.error is None and self.value is not None
