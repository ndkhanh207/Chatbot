from app.compatibility.compat_format import format_compatibility_reply
from app.guard.clarify import _is_compatibility_hallucination


def test_compatibility_guard_allows_plain_verdict():
    context = "- OVERALL_STATUS: compatible"
    raw = "Dạ, combo CPU + Mainboard + GPU này tương thích. Lý do: socket AM5 khớp."

    assert _is_compatibility_hallucination(raw, context) is False


def test_compatibility_guard_allows_answer_with_follow_up():
    context = "- OVERALL_STATUS: compatible"
    raw = (
        "Dạ, combo CPU + Mainboard + GPU này tương thích. "
        "Lý do: socket AM5 khớp, PCIe tương thích. "
        "Bạn muốn em kiểm tra thêm RAM/PSU không?"
    )

    assert _is_compatibility_hallucination(raw, context) is False


def test_format_compatibility_reply_explains_socket_mismatch_plainly():
    context = """[CATALOG_COMPATIBILITY_FACTS]
- OVERALL_STATUS: incompatible
- CPU_MODEL: Intel Core i9-14900K
- CPU_SOCKET: LGA1700
- MAINBOARD_MODEL: MSI B850 PRO
- MAINBOARD_SOCKET: AM5
- SOCKET_MATCH: false
- GPU_MODEL: null
"""

    reply = format_compatibility_reply(context)

    assert reply.startswith("Dạ, Intel Core i9-14900K + MSI B850 PRO không tương thích")
    assert "LGA1700" in reply and "AM5" in reply
    assert "không lắp được" in reply

def test_compatibility_guard_catches_jailbreak_hallucination():
    """
    If the context says KHÔNG TƯƠNG THÍCH, but the raw output says it IS compatible
    (e.g., due to hallucination OR a successful prompt jailbreak), the guard must catch it.
    """
    context = "- OVERALL_STATUS: incompatible"
    raw = "Dạ, CPU và mainboard tương thích hoàn toàn với nhau thưa ngài."

    assert _is_compatibility_hallucination(raw, context) is True
