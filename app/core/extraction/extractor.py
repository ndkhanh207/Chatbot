from time import perf_counter

import ollama
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.extraction.prompts import _FEWSHOT_BY_INTENT, _SYSTEM_EXTRACT
from app.utils.model_utils import get_ollama_model, log_ollama_metrics
from config.config import Config

MAX_TOKENS_EXTRACT = 512


def _get_async_client():
    return ollama.AsyncClient(timeout=Config.OLLAMA_REQUEST_TIMEOUT)


class ExtractedEntities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Kept as `intent` for handler compatibility. It now contains the immutable
    # RoutePlanner handler name, not the output of an intent classifier.
    intent: str = "general_chat"
    target_product: str | None = Field(default=None, max_length=160)
    spec_detail: str | None = Field(default=None, max_length=100)
    cpu: str | None = Field(default=None, max_length=160)
    mainboard: str | None = Field(default=None, max_length=160)
    gpu: str | None = Field(default=None, max_length=160)
    budget_amount: int = Field(default=0)
    category: str | None = Field(default=None, max_length=50)

    @field_validator(
        "target_product", "spec_detail", "cpu", "mainboard", "gpu", "category", mode="before"
    )
    @classmethod
    def normalize_missing_text(cls, value):
        if value is None or (isinstance(value, str) and value.strip().lower() in {"", "none"}):
            return None
        return value

    @model_validator(mode="after")
    def normalize_fields(self) -> "ExtractedEntities":
        if self.intent == "specification" and not self.target_product:
            self.target_product = self.cpu or self.gpu or self.mainboard

        if self.category and self.category.lower() in {
            "price", "specification", "info", "giá", "thông số"
        }:
            self.category = (
                "cpu" if self.cpu else "mainboard" if self.mainboard else "gpu" if self.gpu else None
            )
        return self


class EntityExtractionSchema(BaseModel):
    """Required-key LLM contract; values may be null, keys may not be omitted."""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(description="Copy the selected handler name exactly.")
    target_product: str | None = Field(
        max_length=160,
        description="Product, brand, capacity, or model explicitly named by the user.",
    )
    spec_detail: str | None = Field(
        max_length=100,
        description="Requested technical attribute or performance workload.",
    )
    cpu: str | None = Field(max_length=160, description="Explicit CPU model.")
    mainboard: str | None = Field(max_length=160, description="Explicit mainboard model.")
    gpu: str | None = Field(max_length=160, description="Explicit GPU model.")
    budget_amount: int = Field(description="Budget converted to integer VND, otherwise 0.")
    category: str | None = Field(
        max_length=50,
        description="Requested product category such as cpu, gpu, mainboard, ram, or ssd.",
    )


async def _run_extraction_pass(user_msg: str, handler_name: str) -> ExtractedEntities:
    """Extract entities for a handler already selected by RoutePlanner."""
    fewshots = _FEWSHOT_BY_INTENT.get(handler_name, _FEWSHOT_BY_INTENT["general_chat"])
    prompt = f"<system_hint>Handler = {handler_name}</system_hint>\n<user_input>{user_msg}</user_input>"
    messages = (
        [{"role": "system", "content": _SYSTEM_EXTRACT}]
        + fewshots
        + [{"role": "user", "content": prompt}]
    )
    started = perf_counter()
    response = await _get_async_client().chat(
        model=get_ollama_model(),
        messages=messages,
        options={"temperature": 0.0, "num_predict": MAX_TOKENS_EXTRACT},
        format=EntityExtractionSchema.model_json_schema(),
    )
    log_ollama_metrics("intent_extract", response, perf_counter() - started)
    raw = response["message"]["content"].strip()
    if not raw.endswith("}"):
        raw += "}"
    extracted = EntityExtractionSchema.model_validate_json(raw)
    parsed = ExtractedEntities.model_validate(extracted.model_dump())
    parsed.intent = handler_name
    return parsed
