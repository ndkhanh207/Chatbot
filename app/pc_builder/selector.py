import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from app.catalog import BuildRecord
from app.pc_builder.formatter import format_approx_million
from app.utils.model_utils import get_ollama_model
from app.llm.gateway import safe_llm_call

logger = logging.getLogger(__name__)


class PcBuildSelectionRequest(BaseModel):
    user_message: str
    purpose: str | None = None
    budget: int | None = None


class PcBuildSelection(BaseModel):
    build_id: str = Field(description="One exact BuildID copied from the candidates")
    reason: str | None = Field(
        default=None,
        description="Optional internal reasoning for why this build was selected",
    )


def _candidate_projection(candidate: BuildRecord) -> dict:
    return {
        "build_id": candidate.build_id,
        "components": {
            key: {
                "model": part.model,
                "brand": part.brand,
                "price": part.price,
            }
            for key, part in candidate.components.items()
        },
        "total_price": candidate.total_price,
        "detailed_purpose": candidate.detailed_purpose,
        "notes": candidate.notes,
    }


SELECTOR_PROMPT = """You are a PC build selection assistant.
Your task is to select the BEST matching build from the provided candidates based on the user's request, purpose, and budget.

User Request: {user_message}
Purpose: {purpose}
Budget: {budget}

Candidates:
{candidates_json}

Select exactly one build_id and provide a short internal reason."""


class PcBuildSelector:
    def __init__(self):
        self._llm = ChatOllama(
            model=get_ollama_model(),
            temperature=0,
            num_predict=256,
        ).with_structured_output(PcBuildSelection)

    async def select(
        self,
        request: PcBuildSelectionRequest,
        candidates: list[BuildRecord],
    ) -> PcBuildSelection:
        if not candidates:
            raise ValueError("At least one candidate is required")
            
        if len(candidates) == 1:
            return PcBuildSelection(
                build_id=candidates[0].build_id, 
                reason="Only one candidate available"
            )

        prompt = ChatPromptTemplate.from_messages([
            ("system", SELECTOR_PROMPT)
        ]).format_messages(
            user_message=request.user_message,
            purpose=request.purpose or "Unknown",
            budget=request.budget or "Unknown",
            candidates_json=json.dumps(
                [_candidate_projection(c) for c in candidates], 
                ensure_ascii=False, indent=2
            )
        )
        
        result = await safe_llm_call(
            lambda: self._llm.ainvoke(prompt),
            timeout_seconds=30,
            max_attempts=2,
            operation_name="pc_builder_select"
        )
        
        if result.ok and result.value:
            selected_id = result.value.build_id.casefold()
            valid_ids = {c.build_id.casefold() for c in candidates}
            if selected_id in valid_ids:
                return result.value
                
        logger.warning(
            "Using deterministic selector fallback",
            extra={
                "fallback_build_id": candidates[0].build_id,
                "reason": result.message if not result.ok else "Invalid build_id selected"
            }
        )
        return PcBuildSelection(build_id=candidates[0].build_id, reason="Fallback to first candidate")
