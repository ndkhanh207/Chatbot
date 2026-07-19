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

RERANK_TIMEOUT_SECONDS = 20
_CACHE_SIZE = 128
_RESPONSE_MODES = {"budget_gap", "unavailable", "missing_build", "invalid_budget", "missing_budget", "missing_purpose", "build_qa"}
_decision_cache: OrderedDict[str, "PcBuildDecision"] = OrderedDict()
_structured_llm = None
_turn_llm = None

ComponentCategory = Literal["cpu", "gpu", "mainboard"]


class PcBuildTurnPlan(BaseModel):
    route: Literal["pass", "recommend", "current_build_qa"] = "recommend"
    session_action: Literal["continue", "reset", "alternative"] = "continue"
    budget_action: Literal["keep", "set", "delta", "clear", "invalid"] = "keep"
    budget_value: int | None = None
    quantity: int | None = Field(default=None, ge=1)
    set_components: list[ComponentCategory] = Field(default_factory=list, max_length=3)
    lock_components: list[ComponentCategory] = Field(default_factory=list, max_length=3)
    remove_components: list[ComponentCategory] = Field(default_factory=list, max_length=3)
    mandatory_brands: dict[ComponentCategory | Literal["any"], str] = Field(default_factory=dict)
    remove_brands: list[ComponentCategory | Literal["any"]] = Field(default_factory=list, max_length=4)
    price_order: Literal["asc", "desc"] | None = None

    @model_validator(mode="after")
    def validate_plan(self):
        groups = (
            self.set_components,
            self.lock_components,
            self.remove_components,
        )
        changed = [category for group in groups for category in group]
        if len(changed) != len(set(changed)):
            raise ValueError("A component category can have only one update operation")
        if self.budget_action in {"set", "delta"} and self.budget_value is None:
            raise ValueError("Budget value is required")
        if self.budget_action == "set" and self.budget_value is not None and self.budget_value <= 0:
            raise ValueError("A new budget must be positive")
        if self.budget_action not in {"set", "delta"} and self.budget_value is not None:
            raise ValueError("Budget value is not allowed for this action")
        return self


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

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action == "clarify":
            if not self.clarification_question:
                raise ValueError("A clarification decision requires a question")
            if self.selected_build_id or self.recommendation_reason or self.response_text:
                raise ValueError("A clarification decision cannot select a build")
        elif self.action == "select":
            if not self.selected_build_id or not self.recommendation_reason or not self.response_text:
                raise ValueError("A selection decision requires an ID, reason, and response")
            if self.clarification_question:
                raise ValueError("A selection decision cannot include a question")
        elif not self.response_text:
            raise ValueError("A response decision requires response text")
        elif self.clarification_question or self.selected_build_id or self.recommendation_reason:
            raise ValueError("A response decision cannot clarify or select")
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
        raise ValueError("Response mode requires a response decision")
    facts = response_facts or {}
    response = " ".join((decision.response_text or "").split())
    serialized_facts = json.dumps(facts, ensure_ascii=False, default=str)
    required = []
    if response_mode in {"budget_gap", "invalid_budget"}:
        required = [str(value) for value in facts.values() if value is not None]
    elif response_mode == "unavailable":
        required = [
            str(value)
            for group in (facts.get("components", {}), facts.get("mandatory_brands", {}))
            for value in group.values()
        ]
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
    if response_mode != "build_qa" and (
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
    comparable = [
        json.dumps(
            {key: value for key, value in _candidate_projection(candidate).items() if key != "build_id"},
            ensure_ascii=False,
            sort_keys=True,
        )
        for candidate in candidates
    ]
    if len(set(comparable)) < 2:
        raise ValueError("Clarification cannot change candidate ordering")
    question = " ".join((decision.clarification_question or "").split())
    if (
        len(question) < 8
        or not question.endswith("?")
        or len(re.findall(r"[.!?]+", question)) != 1
    ):
        raise ValueError("Clarification must be one concise question")
    forbidden = [candidate.build_id for candidate in candidates]
    forbidden.extend(
        part.model
        for candidate in candidates
        for part in candidate.components.values()
    )
    lowered = question.casefold()
    if re.search(r"\b(ứng viên|danh sách)\b|khác biệt.{0,20}như thế nào", lowered):
        raise ValueError("Clarification asks the user to analyze candidates")
    if any(value.casefold() in lowered for value in forbidden) or re.search(
        r"₫|\bvnd\b|\btriệu\b", lowered
    ):
        raise ValueError("Clarification contains candidate facts")
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

    response = " ".join((decision.response_text or "").split())
    projection = _candidate_projection(selected)
    selected_facts = (selection_facts or {}).get(selected.build_id, {})
    required_response_values = [
        selected.build_id,
        *(part.model for part in selected.components.values()),
        projection["display_prices"]["total"],
        *(str(value) for value in selected_facts.values() if value is not None),
    ]
    if not all(value.casefold() in response.casefold() for value in required_response_values):
        raise ValueError("Selection response omitted canonical facts")
    serialized = json.dumps(
        {"candidate": projection, "selection_facts": selection_facts or {}},
        ensure_ascii=False,
        default=str,
    )
    allowed_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", serialized))
    if not set(re.findall(r"\d+(?:[.,]\d+)?", response)) <= allowed_numbers:
        raise ValueError("Selection response invented numeric facts")

    return PcBuildDecision(
        action="select",
        selected_build_id=selected.build_id,
        recommendation_reason=reason,
        response_text=response,
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
    global _structured_llm
    if _structured_llm is None:
        llm = ChatOllama(
            model=get_ollama_model(),
            temperature=0,
            top_p=0.05,
            num_predict=512,
            client_kwargs={"timeout": RERANK_TIMEOUT_SECONDS},
        )
        _structured_llm = llm.with_structured_output(PcBuildDecision)
    return _structured_llm


def _get_turn_llm():
    global _turn_llm
    if _turn_llm is None:
        llm = ChatOllama(
            model=get_ollama_model(),
            temperature=0,
            top_p=0.05,
            num_predict=128,
            client_kwargs={"timeout": RERANK_TIMEOUT_SECONDS},
        )
        _turn_llm = llm.with_structured_output(PcBuildTurnPlan)
    return _turn_llm


def _validate_turn_plan(plan: PcBuildTurnPlan, turn: dict) -> PcBuildTurnPlan:
    mentions = turn.get("catalog_mentions", {})
    component_mentions = set(mentions.get("components", {}))
    current = set(turn.get("context", {}).get("required_components", {}))
    current_build = set((turn.get("current_build") or {}).get("components", {}))
    if not set(plan.set_components) <= component_mentions:
        raise ValueError("Turn plan references an unrecognized component")
    if not set(plan.lock_components) <= current_build:
        raise ValueError("Turn plan locks a component outside the current build")
    if not set(plan.remove_components) <= current:
        raise ValueError("Turn plan removes a component that is not constrained")
    brand_mentions = mentions.get("brands", {})
    for category, brand in plan.mandatory_brands.items():
        categories = set(brand_mentions.get(brand, []))
        if not categories or (category != "any" and category not in categories):
            raise ValueError("Turn plan references an unrecognized brand")
    if not set(plan.remove_brands) <= set(turn.get("context", {}).get("mandatory_brands", {})):
        raise ValueError("Turn plan removes a brand that is not constrained")
    return plan


async def plan_build_turn(turn: dict) -> PcBuildTurnPlan:
    messages = PC_BUILD_TURN_TEMPLATE.format_messages(
        turn_json=json.dumps(turn, ensure_ascii=False, separators=(",", ":")),
    )
    try:
        result = await asyncio.wait_for(
            _get_turn_llm().ainvoke(messages),
            timeout=RERANK_TIMEOUT_SECONDS,
        )
        plan = result if isinstance(result, PcBuildTurnPlan) else PcBuildTurnPlan.model_validate(result)
        return _validate_turn_plan(plan, turn)
    except Exception:
        return PcBuildTurnPlan()


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


async def _run_decision(request: dict, candidates: list[BuildRecord]) -> PcBuildDecision:
    response_mode = request.get("response_mode")
    if not candidates and response_mode not in {"unavailable", "missing_build", "invalid_budget"}:
        raise ValueError("At least one build candidate is required")

    key = _cache_key(request, candidates)
    if cached := _decision_cache.get(key):
        _decision_cache.move_to_end(key)
        return cached

    start_time = time.time()
    try:
        decision = await asyncio.wait_for(
            _invoke_model(request, candidates),
            timeout=RERANK_TIMEOUT_SECONDS,
        )
        if response_mode:
            decision = _validate_response(
                decision, candidates, response_mode, request.get("response_facts")
            )
        else:
            decision = _validate_decision(
                decision,
                candidates,
                bool(request.get("force_select")),
                request.get("selection_facts"),
            )
            
        reranker_latency = time.time() - start_time
        logger.info(
            f"Reranker success | retrieved_candidates: {[c.build_id for c in candidates]} | "
            f"selected_id: {decision.selected_build_id} | latency: {reranker_latency:.2f}s"
        )
        
    except asyncio.TimeoutError as e:
        logger.warning(f"Reranker timeout after {time.time() - start_time:.2f}s")
        raise BuildSelectionError("Reranker timeout") from e
    except Exception as e:
        logger.warning(f"Reranker failure: {e}")
        if response_mode:
            raise
        raise BuildSelectionError(f"Reranker failed: {e}") from e

    _decision_cache[key] = decision
    _decision_cache.move_to_end(key)
    if len(_decision_cache) > _CACHE_SIZE:
        _decision_cache.popitem(last=False)
    return decision


async def choose_build(request: dict, candidates: list[BuildRecord]) -> PcBuildDecision:
    """Choose between clarifying and selecting from valid catalog candidates."""
    if request.get("response_mode"):
        raise ValueError("Use write_build_response for factual responses")
    if not candidates:
        raise ValueError("At least one build candidate is required")
        
    try:
        return await _run_decision(request, candidates)
    except BuildSelectionError as e:
        logger.warning(f"Fallback to candidates[0] due to BuildSelectionError: {e}")
        return _fallback(candidates)


async def write_build_response(
    mode: str,
    facts: dict,
    candidates: list[BuildRecord] | None = None,
    user_message: str | None = None,
) -> str:
    """Write guarded factual prose without exposing decision fields to callers."""
    if mode not in _RESPONSE_MODES:
        raise ValueError("Unknown response mode")
        
    request_data = {"response_mode": mode, "response_facts": facts, "user_message": user_message or ""}
    
    if mode in ("invalid_budget", "budget_gap"):
        request_data["instruction"] = "Ngân sách quá thấp. BẮT BUỘC dùng cụm từ 'cao hơn ngân sách' hoặc 'tăng ngân sách' hoặc 'mâu thuẫn' trong câu trả lời."
    elif mode == "unavailable":
        request_data["instruction"] = "Không tìm thấy cấu hình. BẮT BUỘC dùng cụm từ 'chưa có' hoặc 'không tìm thấy' hoặc 'không tìm' trong câu trả lời. BẮT BUỘC nhắc lại tên tất cả các linh kiện có trong facts."
    elif mode == "missing_budget":
        request_data["instruction"] = "Báo khách hàng cung cấp ngân sách."
    elif mode == "missing_purpose":
        request_data["instruction"] = "Báo khách hàng cung cấp mục đích sử dụng."
    elif mode == "missing_build":
        request_data["instruction"] = "Báo khách hàng rằng chưa xác định được cấu hình nào đang được nhắc đến."

    decision = await _run_decision(
        request_data,
        candidates or [],
    )
    return decision.response_text or decision.recommendation_reason or "Dạ em đã ghi nhận thông tin."
