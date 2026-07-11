from app.core.intent.master_intent import (
    MasterIntentSchema,
    _apply_post_extraction_guards,
    _count_components,
)


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
