from typing import Literal
from pydantic import BaseModel
from app.core.intent.master_intent import MasterIntentSchema

LlmErrorKind = Literal[
    "timeout",
    "validation_error",
    "parsing_error",
    "unknown"
]

class IntentResult(BaseModel):
    value: MasterIntentSchema | None = None
    error: LlmErrorKind | None = None
    source: Literal[
        "fast_path",
        "llm",
        "fallback",
    ]

    @property
    def ok(self) -> bool:
        return self.error is None and self.value is not None
