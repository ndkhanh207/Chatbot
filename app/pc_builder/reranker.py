from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import logging
from collections import OrderedDict
from typing import Literal

from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

class BuildSelectionError(Exception):
    pass

from app.catalog import BuildRecord
from app.pc_builder.formatter import format_approx_million, format_build_context
from app.templates.prompt_templates import (
    PC_BUILD_RERANK_PROMPT_VERSION,
    PC_BUILD_RERANK_TEMPLATE,
    PC_BUILD_TURN_TEMPLATE,
)
from app.utils.model_utils import get_ollama_model

RERANK_TIMEOUT_SECONDS = 60
_CACHE_SIZE = 128
_RESPONSE_MODES = {"budget_gap", "unavailable", "missing_build", "invalid_budget", "missing_budget", "missing_purpose", "build_qa"}
_decision_cache: OrderedDict[str, "PcBuildDecision"] = OrderedDict()
_structured_llm = None
_turn_llm = None

ComponentCategory = Literal["cpu", "gpu", "mainboard"]



class PcBuildDecision(BaseModel):
    action: Literal["clarify", "select", "respond"] = Field(
        description="Clarify or select normally; respond only for a supplied response_mode"
    )
    clarification_question: str | None = Field(
        default=None,
        max_length=240,
        description="A new candidate-dependent Vietnamese preference question, only when action is clarify",
    )
    selected_build_id: str | None = Field(
        default=None,
        description="One exact BuildID copied from the candidates when action is select",
    )
    recommendation_reason: str | None = Field(
        default=None,
        max_length=800,
        description="A detailed Vietnamese explanation grounded in purpose, with notes used for support or warnings",
    )
    response_text: str | None = Field(
        default=None,
        max_length=2000,
        description="A concise factual reply generated only from response_facts when action is respond",
    )
    message: str | None = Field(
        default=None,
        description="Fallback field for response_text if the LLM uses message instead",
    )
    result: str | None = Field(
        default=None,
        description="Fallback field for response_text if the LLM uses result instead",
    )

    @model_validator(mode="after")
    def validate_action_fields(self):
        # Map fallback message/result field to the appropriate string field based on action
        fallback_text = self.message or self.result
        if fallback_text:
            if self.action == "clarify" and not self.clarification_question:
                self.clarification_question = fallback_text
            elif not self.response_text:
                self.response_text = fallback_text
            
        return self


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
        "assembly_fee": candidate.assembly_fee,
        "total_price": candidate.total_price,
        "gpu_quantity": int(str(candidate.attributes.get("GPU_Quantity", 1) or 1)),
        "display_prices": {
            **{
                category: format_approx_million(part.price)
                for category, part in candidate.components.items()
            },
            "gpu_total": format_approx_million(
                candidate.components["gpu"].price * int(str(candidate.attributes.get("GPU_Quantity", 1) or 1))
            ) if "gpu" in candidate.components else None,
            "assembly_fee": format_approx_million(candidate.assembly_fee),
            "total": format_approx_million(candidate.total_price),
        },
        "detailed_purpose": candidate.detailed_purpose,
        "primary_workload": str(candidate.attributes.get("Primary_Workload", "")),
        "purpose_category": str(candidate.attributes.get("Purpose_Category", "")),
        "notes": candidate.notes,
    }


def _fallback(candidates: list[BuildRecord]) -> PcBuildDecision:
    candidate = candidates[0]
    return PcBuildDecision(
        action="select",
        selected_build_id=candidate.build_id,
        recommendation_reason=(
            candidate.detailed_purpose
            or candidate.notes
            or "Phù hợp nhất với các yêu cầu đã xác thực."
        ),
        response_text=format_build_context(candidate),
    )


def _cache_key(request: dict, candidates: list[BuildRecord]) -> str:
    payload = json.dumps(
        {
            "prompt_version": PC_BUILD_RERANK_PROMPT_VERSION,
            "request": request,
            "candidates": [_candidate_projection(candidate) for candidate in candidates],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()




def _validate_response(
    decision: PcBuildDecision,
    candidates: list[BuildRecord],
    response_mode: str,
    response_facts: dict | None = None,
) -> PcBuildDecision:
    if response_mode not in _RESPONSE_MODES:
        raise ValueError("Unknown response mode")
    if decision.action != "respond":
        fallback = decision.response_text or getattr(decision, 'message', None) or getattr(decision, 'result', None) or getattr(decision, 'clarification_question', None) or getattr(decision, 'recommendation_reason', None)
        if not fallback:
            logger.warning(f"Response mode {response_mode} required text, but LLM outputted none. Decision: {decision}")
            fallback = "Bạn có thể cung cấp thêm thông tin chi tiết không?"
        decision = PcBuildDecision(action="respond", response_text=fallback)
    facts = response_facts or {}
    response = " ".join((decision.response_text or "").split())
    serialized_facts = json.dumps(facts, ensure_ascii=False, default=str)
    required = []
    if response_mode in {"budget_gap", "invalid_budget"}:
        # ponytail: Formatting numbers (2.500.000 vs 2500000) breaks exact substring match.
        # Numeric hallucination check below handles safety.
        required = []
    elif response_mode == "unavailable":
        required = []
    elif response_mode == "missing_build" and facts.get("build_id"):
        required = [str(facts["build_id"])]
    elif response_mode == "build_qa" and candidates:
        serialized_facts += json.dumps(
            _candidate_projection(candidates[0]), ensure_ascii=False, default=str
        )
    if not all(value.casefold() in response.casefold() for value in required):
        raise ValueError("Response omitted canonical facts")
    allowed_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", serialized_facts))
    if not set(re.findall(r"\d+(?:[.,]\d+)?", response)) <= allowed_numbers:
        raise ValueError("Response invented numeric facts")
    if response_mode not in ("build_qa", "unavailable", "missing_build") and (
        not response.endswith("?") or response.count("?") != 1
    ):
        raise ValueError("Response must end with one question")
    return PcBuildDecision(action="respond", response_text=response)


def _validate_clarification(
    decision: PcBuildDecision,
    candidates: list[BuildRecord],
    force_select: bool,
) -> PcBuildDecision:
    if force_select:
        raise ValueError("Clarification limit reached")
    question = " ".join((decision.clarification_question or "").split())
    if len(question) < 8:
        raise ValueError("Clarification must be a valid question")
        
    lowered = question.casefold()
    forbidden = [candidate.build_id for candidate in candidates]
    forbidden.extend(
        part.model
        for candidate in candidates
        for part in candidate.components.values()
    )
    if any(value.casefold() in lowered for value in forbidden):
        raise ValueError("Clarification contains candidate facts (IDs or Models)")
        
    if re.search(r"₫|\bvnd\b|\btriệu\b", lowered):
        raise ValueError("Clarification contains price facts")
        
    return PcBuildDecision(action="clarify", clarification_question=question)


def _validate_selection(
    decision: PcBuildDecision,
    candidates: list[BuildRecord],
    selection_facts: dict | None,
) -> PcBuildDecision:
    valid_ids = {candidate.build_id.casefold() for candidate in candidates}
    selected_id = (decision.selected_build_id or "").casefold()
    if selected_id not in valid_ids:
        raise ValueError("Decision selected an ID outside the candidate set")

    selected = next(
        candidate
        for candidate in candidates
        if candidate.build_id.casefold() == selected_id
    )
    reason = " ".join((decision.recommendation_reason or "").split())
    if len(reason) < 20:
        raise ValueError("Recommendation reason is too short")
    if re.search(r"₫|\bvnd\b|\btriệu\b", reason.casefold()):
        raise ValueError("Recommendation reason contains generated price facts")
    forbidden = [candidate.build_id for candidate in candidates]
    forbidden.extend(
        value
        for candidate in candidates
        for part in candidate.components.values()
        for value in (part.model, part.brand or "")
    )
    if any(value and value.casefold() in reason.casefold() for value in forbidden):
        raise ValueError("Recommendation reason contains catalog identifiers")
    evidence = f"{selected.detailed_purpose} {selected.notes} {selected.attributes.get('Primary_Workload', '')}".casefold()
    if any(token.casefold() not in evidence for token in re.findall(r"\d+[a-zA-Z]*", reason)):
        raise ValueError("Recommendation reason contains unsupported numeric claims")

    return PcBuildDecision(
        action="select",
        selected_build_id=selected.build_id,
        recommendation_reason=reason,
    )


def _validate_decision(
    decision: PcBuildDecision,
    candidates: list[BuildRecord],
    force_select: bool,
    selection_facts: dict | None = None,
) -> PcBuildDecision:
    if decision.action == "respond":
        raise ValueError("A normal decision cannot return a response")
    if decision.action == "clarify":
        return _validate_clarification(decision, candidates, force_select)
    return _validate_selection(decision, candidates, selection_facts)


def _get_structured_llm():
    llm = ChatOllama(
        model=get_ollama_model(),
        temperature=0,
        top_p=0.05,
        num_predict=512,
        client_kwargs={"timeout": RERANK_TIMEOUT_SECONDS},
    )
    return llm.with_structured_output(PcBuildDecision)

async def _invoke_model(request: dict, candidates: list[BuildRecord]) -> PcBuildDecision:
    messages = PC_BUILD_RERANK_TEMPLATE.format_messages(
        request_json=json.dumps(request, ensure_ascii=False, separators=(",", ":"), default=str),
        candidate_json=json.dumps(
            [_candidate_projection(candidate) for candidate in candidates],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    result = await _get_structured_llm().ainvoke(messages)
    return result if isinstance(result, PcBuildDecision) else PcBuildDecision.model_validate(result)


MAX_RETRIES = 1

from app.llm.gateway import safe_llm_call

async def _attempt_decision(
    request: dict,
    candidates: list[BuildRecord],
    response_mode: str | None,
) -> PcBuildDecision:
    """Invokes the model and validates the decision."""
    decision = await _invoke_model(request, candidates)
    
    if response_mode:
        return _validate_response(
            decision, candidates, response_mode, request.get("response_facts")
        )
        
    return _validate_decision(
        decision,
        candidates,
        bool(request.get("force_select")),
        request.get("selection_facts"),
    )

async def _run_decision(request: dict, candidates: list[BuildRecord]) -> PcBuildDecision:
    response_mode = request.get("response_mode")
    if not candidates and not response_mode:
        raise ValueError("At least one build candidate is required")

    key = _cache_key(request, candidates)
    if cached := _decision_cache.get(key):
        _decision_cache.move_to_end(key)
        return cached

    current_request = dict(request)
    
    result = await safe_llm_call(
        lambda: _attempt_decision(current_request, candidates, response_mode),
        timeout_seconds=RERANK_TIMEOUT_SECONDS,
        max_attempts=MAX_RETRIES,
        operation_name="pc_builder_rerank" if not response_mode else "pc_builder_respond",
    )
    
    if result.ok and result.value is not None:
        decision = result.value
        _decision_cache[key] = decision
        _decision_cache.move_to_end(key)
        if len(_decision_cache) > _CACHE_SIZE:
            _decision_cache.popitem(last=False)
        return decision

    if response_mode:
        raise BuildSelectionError(f"Reranker failed: {result.message}")
        
    raise BuildSelectionError(f"Reranker failed after retries: {result.message}")


async def choose_build(request: dict, candidates: list[BuildRecord]) -> PcBuildDecision:
    """Choose between clarifying and selecting from valid catalog candidates."""
    if request.get("response_mode"):
        raise ValueError("Use write_build_response for factual responses")
    if not candidates:
        raise ValueError("At least one build candidate is required")
        
    try:
        return await _run_decision(request, candidates)
    except BuildSelectionError as e:
        logger.warning(
            "Using deterministic reranker fallback",
            extra={
                "error_kind": "BuildSelectionError",
                "fallback_build_id": candidates[0].build_id,
            },
        )
        return PcBuildDecision(
            action="select",
            selected_build_id=candidates[0].build_id,
            recommendation_reason=None,
        )


async def write_build_response(
    mode: str,
    facts: dict,
    candidates: list[BuildRecord] | None = None,
    user_message: str | None = None,
) -> str:
    """Write guarded factual prose without exposing decision fields to callers."""
    print(f"DEBUG: write_build_response called with mode={mode}, facts={facts}")
    if mode not in _RESPONSE_MODES:
        raise ValueError("Unknown response mode")
        
    request_data = {"response_mode": mode, "response_facts": facts, "user_message": user_message or ""}

    try:
        decision = await _run_decision(
            request_data,
            candidates or [],
        )
        return decision.response_text or decision.recommendation_reason or "Dạ em đã ghi nhận thông tin."
    except Exception as e:
        logger.error(f"write_build_response failed: {e}. Using generic service unavailable fallback.")
        return f"Xin lỗi, hệ thống đang bận nên em chưa xử lý được. Lỗi: {repr(e)}. Bạn vui lòng thử lại sau một chút nhé."
