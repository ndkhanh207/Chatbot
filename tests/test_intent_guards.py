import asyncio

import ollama
import pytest

from app.core.intent import master_intent
from app.core.intent.master_intent import (
    MasterIntentSchema,
    _apply_pre_extraction_guards,
    _apply_post_extraction_guards,
    _check_retry_condition,
    _count_components,
    _has_explicit_build,
    _inherit_structured_followup_state,
    _run_extraction_pass,
)
from app.specification.field_resolver import resolve_explicit_spec_detail


def test_compatibility_regex_rescue_keeps_branded_gpu():
    msg = (
        "amd ryzen 5 9600x + msi b850 pro b850m-vc wifi6e am5 ddr5 micro atx "
        "+ msi gaming trio geforce rtx 4080 16gb gddr6x black có tương thích với nhau không?"
    )
    comp_count, cpu_match, gpu_match, main_match = _count_components(msg)
    parsed = MasterIntentSchema(
        intent="compatibility",
        cpu="amd ryzen 5 9600x",
        mainboard="msi b850 pro b850m-vc wifi6e am5 ddr5 micro atx",
        gpu="none",
    )

    _apply_post_extraction_guards(parsed, cpu_match, gpu_match, main_match, comp_count)

    assert parsed.gpu == "msi gaming trio geforce rtx 4080 16gb gddr6x black"


def test_explicit_followup_mainboard_replaces_copied_state():
    msg = "thế còn main asus b760m-ayw thì sao?"
    comp_count, cpu_match, gpu_match, main_match = _count_components(msg)
    parsed = MasterIntentSchema(
        intent="compatibility",
        cpu="ryzen 5 7600x",
        mainboard="msi pro b650m-p",
    )

    _apply_post_extraction_guards(parsed, cpu_match, gpu_match, main_match, comp_count)

    assert parsed.mainboard == "asus b760m-ayw"


@pytest.mark.parametrize(
    ("message", "expected_detail"),
    [
        ("thế còn xung nhịp?", "xung nhịp"),
        ("socket của nó là gì?", "socket"),
        ("nó có bao nhiêu vram?", "bộ nhớ"),
        ("công suất tiêu thụ thế nào?", "tdp"),
        ("chuẩn giao tiếp của nó?", "chuẩn giao tiếp"),
    ],
)
def test_spec_detail_resolver_uses_shared_aliases(message, expected_detail):
    assert resolve_explicit_spec_detail(message) == expected_detail


@pytest.mark.parametrize(
    ("message", "expected_detail"),
    [
        ("thế còn xung nhịp?", "xung nhịp"),
        ("socket của nó thì sao?", "socket"),
        ("công suất tiêu thụ thì sao?", "tdp"),
    ],
)
def test_spec_followup_keeps_product_and_uses_explicit_detail(message, expected_detail):
    parsed = MasterIntentSchema(
        intent="specification",
        spec_detail="cpu",
        cpu="intel core i7-4770",
        category="cpu",
    )
    state = {
        "target_product": "rtx 5070 ti",
        "gpu": "rtx 5070 ti",
        "category": "gpu",
        "spec_detail": "vram",
    }

    _inherit_structured_followup_state(parsed, state, None, None, None, message)

    assert parsed.target_product == "rtx 5070 ti"
    assert parsed.category == "gpu"
    assert parsed.spec_detail == expected_detail
    assert parsed.cpu is None


@pytest.mark.parametrize("previous_detail", ["xung nhịp", "màu", "tdp", "bộ nhớ"])
def test_vague_new_product_inherits_previous_spec_detail(previous_detail):
    msg = "vậy của rtx 5080 thì sao?"
    comp_count, cpu_match, gpu_match, main_match = _count_components(msg)
    parsed = MasterIntentSchema(
        intent="specification",
    )
    state = {
        "target_product": "rtx 5070 ti",
        "gpu": "rtx 5070 ti",
        "category": "gpu",
        "spec_detail": previous_detail,
    }

    _apply_post_extraction_guards(parsed, cpu_match, gpu_match, main_match, comp_count)
    _inherit_structured_followup_state(
        parsed, state, cpu_match, gpu_match, main_match, msg
    )

    assert parsed.target_product == "rtx 5080"
    assert parsed.category == "gpu"
    assert parsed.spec_detail == previous_detail


def test_compat_followup_rejects_copied_future_cpu():
    msg = "thế còn main asus b760m-ayw thì sao?"
    comp_count, cpu_match, gpu_match, main_match = _count_components(msg)
    parsed = MasterIntentSchema(
        intent="compatibility",
        cpu="i7 14700k",
        mainboard="b650m-p",
    )
    state = {"cpu": "ryzen 5 7600x", "mainboard": "msi pro b650m-p"}

    _apply_post_extraction_guards(parsed, cpu_match, gpu_match, main_match, comp_count)
    _inherit_structured_followup_state(
        parsed, state, cpu_match, gpu_match, main_match, msg
    )

    assert parsed.cpu == "ryzen 5 7600x"
    assert parsed.mainboard == "asus b760m-ayw"


def test_retry_condition_counts_duplicate_product_once():
    parsed = MasterIntentSchema(
        intent="compatibility",
        cpu="i5-12400f",
        target_product="i5 12400f",
    )

    assert _check_retry_condition(parsed) == "suggestion"


def test_retry_condition_keeps_two_unique_products():
    parsed = MasterIntentSchema(
        intent="compatibility",
        cpu="i5 12400f",
        target_product="rtx 4060",
    )

    assert _check_retry_condition(parsed) is None


def test_pre_guard_reads_last_intent_and_category_from_structured_state():
    result = _apply_pre_extraction_guards(
        msg_l="có loại nào tầm 10 triệu không",
        comp_count=0,
        intent_pass1="build_pc",
        structured_state={"last_intent": "general_search", "category": "gpu"},
    )

    assert result == "budget_search"


@pytest.mark.parametrize(
    ("message", "expected"),
    [("PCIe 5.0", False), ("tư vấn pc 20 triệu", True)],
)
def test_build_trigger_requires_word_boundary(message, expected):
    assert _has_explicit_build(message) is expected


def test_master_schema_uses_null_for_missing_entities():
    parsed = MasterIntentSchema(intent="none", cpu="none")

    assert parsed.cpu is None
    assert "reasoning" not in MasterIntentSchema.model_json_schema()["properties"]


def test_general_search_category_inheritance_is_deterministic():
    parsed = MasterIntentSchema(intent="general_search", target_product="corsair")

    _inherit_structured_followup_state(
        parsed,
        {"category": "ram"},
        None,
        None,
        None,
        "thế còn của hãng corsair thì sao?",
    )

    assert parsed.category == "ram"


def test_none_intent_does_not_inherit_stale_category():
    parsed = MasterIntentSchema(intent="none")

    _inherit_structured_followup_state(parsed, {"category": "gpu"}, None, None, None, "xin chào")

    assert parsed.category is None


def test_combo_review_inherits_verified_components():
    parsed = MasterIntentSchema(intent="combo_review")
    state = {"cpu": "ryzen 7 9800x3d", "mainboard": "msi b850", "gpu": "rtx 4080"}

    _inherit_structured_followup_state(parsed, state, None, None, None, "đánh giá bộ pc này")

    assert (parsed.cpu, parsed.mainboard, parsed.gpu) == tuple(state.values())


def test_extraction_pass_receives_current_message_only(monkeypatch):
    captured = {}

    async def fake_chat(**kwargs):
        captured.update(kwargs)
        return {"message": {"content": '{"intent":"price_check","target_product":"rtx 4060"}'}}

    monkeypatch.setattr(master_intent._async_client, "chat", fake_chat)

    parsed = asyncio.run(_run_extraction_pass("giá rtx 4060", "price_check"))

    assert parsed.target_product == "rtx 4060"
    assert captured["messages"][-1]["content"] == (
        "<system_hint>Intent = price_check</system_hint>\n<user_input>giá rtx 4060</user_input>"
    )
    assert all("STRUCTURED_STATE" not in message["content"] for message in captured["messages"])


def test_expected_ollama_error_falls_back_to_none(monkeypatch):
    async def unavailable(*args, **kwargs):
        raise ollama.RequestError("offline")

    monkeypatch.setattr(master_intent, "_run_classification_pass", unavailable)

    parsed = asyncio.run(master_intent.parse_master_intent("hello"))

    assert parsed.intent == "none"


def test_programming_error_is_not_hidden_as_none(monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("programming bug")

    monkeypatch.setattr(master_intent, "_run_classification_pass", broken)

    with pytest.raises(RuntimeError, match="programming bug"):
        asyncio.run(master_intent.parse_master_intent("hello"))
