from app.compatibility.compat_format import format_compatibility_reply
from app.guard.clarify import _is_compatibility_hallucination


def test_compatibility_guard_allows_plain_verdict():
    context = "- KẾT LUẬN TỔNG THỂ: TƯƠNG THÍCH (PHÙ HỢP)"
    raw = "Dạ, combo CPU + Mainboard + GPU này tương thích. Lý do: socket AM5 khớp."

    assert _is_compatibility_hallucination(raw, context) is False


def test_compatibility_guard_allows_answer_with_follow_up():
    context = "- KẾT LUẬN TỔNG THỂ: TƯƠNG THÍCH (PHÙ HỢP)"
    raw = (
        "Dạ, combo CPU + Mainboard + GPU này tương thích. "
        "Lý do: socket AM5 khớp, PCIe tương thích. "
        "Bạn muốn em kiểm tra thêm RAM/PSU không?"
    )

    assert _is_compatibility_hallucination(raw, context) is False


def test_format_compatibility_reply_explains_socket_mismatch_plainly():
    context = """[KIỂM TRA TƯƠNG THÍCH COMBO 3 LINH KIỆN]
- KẾT LUẬN TỔNG THỂ: KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP)
- CPU + Mainboard: KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP)
- CHI TIẾT CPU + Mainboard: KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP): Socket không khớp. CPU dùng LGA1700, mainboard dùng AM5.
- GPU + Mainboard: TƯƠNG THÍCH (PHÙ HỢP)
- CHI TIẾT GPU + Mainboard: GPU và mainboard dùng chuẩn PCIe tương thích.
- CPU + GPU: TƯƠNG THÍCH (PHÙ HỢP)
- CHI TIẾT CPU + GPU: CPU và GPU cân bằng theo tier, không thấy cảnh báo nghẽn rõ rệt.
"""

    reply = format_compatibility_reply(context)

    assert reply.startswith("Dạ, combo này không tương thích")
    assert "[KIỂM TRA" not in reply
    assert "khác chuẩn chân cắm" in reply
    assert "không dùng được" in reply

def test_compatibility_guard_catches_jailbreak_hallucination():
    """
    If the context says KHÔNG TƯƠNG THÍCH, but the raw output says it IS compatible
    (e.g., due to hallucination OR a successful prompt jailbreak), the guard must catch it.
    """
    context = "- KẾT LUẬN TỔNG THỂ: KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP)"
    raw = "Dạ, CPU và mainboard tương thích hoàn toàn với nhau thưa ngài."

    assert _is_compatibility_hallucination(raw, context) is True
