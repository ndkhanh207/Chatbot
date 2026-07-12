import pytest

from app.core.intent.master_intent import (
    MasterIntentSchema,
    _apply_post_extraction_guards,
    _count_components,
    _inherit_structured_followup_state,
)
from app.specification.field_resolver import resolve_explicit_spec_detail


def test_compatibility_regex_rescue_keeps_branded_gpu():
    msg = (
        "amd ryzen 5 9600x + msi b850 pro b850m-vc wifi6e am5 ddr5 micro atx "
        "+ msi gaming trio geforce rtx 4080 16gb gddr6x black có tương thích với nhau không?"
    )
    comp_count, cpu_match, gpu_match, main_match = _count_components(msg)
    parsed = MasterIntentSchema(
        reasoning="mock",
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
        reasoning="mock",
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
        reasoning="mock",
        intent="specification",
        target_product="none",
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
    assert parsed.cpu == "none"


@pytest.mark.parametrize("previous_detail", ["xung nhịp", "màu", "tdp", "bộ nhớ"])
def test_vague_new_product_inherits_previous_spec_detail(previous_detail):
    msg = "vậy của rtx 5080 thì sao?"
    comp_count, cpu_match, gpu_match, main_match = _count_components(msg)
    parsed = MasterIntentSchema(
        reasoning="mock",
        intent="specification",
        target_product="none",
        spec_detail="none",
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
        reasoning="copied few-shot",
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
