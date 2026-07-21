import ollama
from pydantic import ValidationError
from app.core.intent.master_intent import (
    MasterIntentSchema,
    _run_classification_pass,
    _run_extraction_pass,
    _apply_pre_extraction_guards,
    _apply_post_extraction_guards,
    _inherit_structured_followup_state,
    _check_retry_condition,
    _handle_retry,
    _count_components,
    _has_explicit_build,
    COMPAT_TRIGGERS,
    REVIEW_TRIGGERS,
    BUDGET_TRIGGERS,
    PRICE_TRIGGERS,
)
from app.core.intent.history_context import extract_structured_state, build_history_context
from app.core.intent.models import IntentResult

class IntentService:
    async def parse(
        self,
        *,
        message: str,
        history: list,
    ) -> IntentResult:
        
        msg_l = message.lower()
        
        # 1. Fast Paths & Deterministic Regex Guards
        structured_state = extract_structured_state(history)
        comp_count, cpu_match, gpu_match, main_match = _count_components(msg_l)

        has_compat_trigger = any(t in msg_l for t in COMPAT_TRIGGERS)
        has_review_trigger = any(t in msg_l for t in REVIEW_TRIGGERS)
        is_explicit_build = _has_explicit_build(msg_l)
        has_price_trigger = any(t in msg_l for t in PRICE_TRIGGERS)
        has_full_combo = structured_state.get("cpu", "none") != "none" and structured_state.get("gpu", "none") != "none" and structured_state.get("mainboard", "none") != "none"

        intent_pass1 = "none"
        if has_compat_trigger and comp_count >= 2:
            intent_pass1 = "compatibility"
        elif has_review_trigger and (comp_count >= 3 or has_full_combo):
            intent_pass1 = "combo_review"
        elif is_explicit_build:
            intent_pass1 = "build_pc"
        elif ('tổng' in msg_l or 'cộng' in msg_l) and has_price_trigger and comp_count >= 2:
            intent_pass1 = "price_calculation"
        elif has_price_trigger and comp_count >= 1:
            intent_pass1 = "price_check"

        if intent_pass1 != "none":
            print(f"⚡ [FAST-PATH] Heuristic bắt được intent: {intent_pass1}")
            if intent_pass1 == "build_pc":
                return IntentResult(
                    value=MasterIntentSchema(intent="build_pc"),
                    source="fast_path"
                )
        
        # 2. LLM Classification Pass
        try:
            if intent_pass1 == "none":
                history_context = build_history_context(history)
                intent_pass1 = await _run_classification_pass(message, history_context)

            # Pre-extraction Guards
            intent_pass1 = _apply_pre_extraction_guards(msg_l, comp_count, intent_pass1, structured_state)

            if intent_pass1 == "build_pc":
                return IntentResult(
                    value=MasterIntentSchema(intent="build_pc"),
                    source="llm"
                )
                
            # 3. LLM Extraction Pass
            parsed = await _run_extraction_pass(message, intent_pass1)
            parsed.intent = intent_pass1 
            
            # Post-extraction Guards
            _apply_post_extraction_guards(parsed, cpu_match, gpu_match, main_match, comp_count)
            _inherit_structured_followup_state(parsed, structured_state, cpu_match, gpu_match, main_match, msg_l)

            # Retry Logic
            fallback_intent = _check_retry_condition(parsed)
            if fallback_intent:
                parsed = await _handle_retry(message, parsed, fallback_intent)
                _apply_post_extraction_guards(parsed, cpu_match, gpu_match, main_match, comp_count)
                _inherit_structured_followup_state(parsed, structured_state, cpu_match, gpu_match, main_match, msg_l)

            return IntentResult(
                value=parsed,
                source="llm"
            )
            
        except TimeoutError:
            return IntentResult(error="timeout", source="llm")
        except ValidationError:
            return IntentResult(error="validation_error", source="llm")
        except (ollama.RequestError, ollama.ResponseError):
            return IntentResult(error="parsing_error", source="llm")
        except Exception:
            return IntentResult(error="unknown", source="llm")
