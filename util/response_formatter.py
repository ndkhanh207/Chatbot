# response_formatter.py
"""
Phát hiện loại query và build format_hint động.
Được inject vào {format_hint} trong ADVISOR_TEMPLATE.
"""

import re
from typing import Optional

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
NUMERIC_SPEC_SIGNALS = {
    "xung boost":         "MHz",
    "xung cơ bản":        "MHz",
    "xung nhân":          "MHz",
    "xung bộ nhớ":        "MHz",
    "boost clock":        "MHz",
    "base clock":         "MHz",
    "tdp":                "W",
    "công suất":          "W",
    "vram":               "GB",
    "dung lượng":         "GB",
    "tốc độ ram":         "MHz",
    "tốc độ đọc":         "MB/s",
    "tốc độ ghi":         "MB/s",
}

SPEC_QUERY_TRIGGERS = [
    "bao nhiêu", "là bao nhiêu", "thông số",
    "nhanh nhất", "cao nhất", "thấp nhất", "mạnh nhất",
    "xung", "tốc độ", "so sánh",
]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def detect_spec_field(user_message: str) -> tuple[Optional[str], Optional[str]]:
    """Trả về (field_name, unit) nếu user hỏi về thông số số cụ thể."""
    msg_lower = user_message.lower()
    for field, unit in NUMERIC_SPEC_SIGNALS.items():
        if field in msg_lower:
            return field, unit
    return None, None


def is_spec_range_query(user_message: str, matched_items: list) -> bool:
    """True khi user hỏi thông số của nhiều sản phẩm cùng lúc."""
    if len(matched_items) <= 1:
        return False
    msg_lower = user_message.lower()
    has_trigger = any(t in msg_lower for t in SPEC_QUERY_TRIGGERS)
    field, _ = detect_spec_field(user_message)
    return has_trigger and field is not None


def build_range_summary(user_message: str, matched_items: list) -> str:
    """
    Tính min/max từ data thực tế (không để LLM tự tính tránh sai).
    Trả về string tóm tắt range.
    """
    field, unit = detect_spec_field(user_message)
    if not field:
        return ""

    entries = []
    for item in matched_items:
        name = item.get("tên") or item.get("name", "???")
        for key, val in item.items():
            if field in key.lower() and isinstance(val, (int, float)) and val > 0:
                entries.append((name, round(val, 2), unit))
                break

    if not entries:
        return ""

    values  = [e[1] for e in entries]
    min_val = min(values)
    max_val = max(values)

    lines = []
    if min_val != max_val:
        lines.append(
            f"📊 TỔNG HỢP: {field} nằm trong khoảng "
            f"{min_val} – {max_val} {unit}."
        )
    else:
        lines.append(
            f"📊 TỔNG HỢP: Tất cả sản phẩm đều có {field} = {min_val} {unit}."
        )

    lines.append("Chi tiết từng sản phẩm (sắp xếp từ cao đến thấp):")
    for name, val, u in sorted(entries, key=lambda x: x[1], reverse=True):
        lines.append(f"  • {name}: {val} {u}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Main — được gọi từ chat_handler
# ──────────────────────────────────────────────
def build_format_hint(user_message: str, matched_items: list) -> str:
    """
    Trả về format_hint để inject vào {format_hint} trong template.
    Trả về chuỗi rỗng "" nếu không cần format đặc biệt.
    """
    if not is_spec_range_query(user_message, matched_items):
        return ""  # template hiển thị rỗng, không ảnh hưởng gì

    field, _ = detect_spec_field(user_message)
    range_summary = build_range_summary(user_message, matched_items)

    return f"""
    [DỮ LIỆU ĐÃ TỔNG HỢP SẴN - Dùng làm cơ sở trả lời, KHÔNG tự tính lại]
    {range_summary}

    [HƯỚNG DẪN ĐỊNH DẠNG BẮT BUỘC]
    1. Câu đầu tiên: nêu khoảng giá trị tổng hợp ở trên.
    2. Tiếp theo: liệt kê từng sản phẩm từ cao đến thấp.
    3. KHÔNG gọi một sản phẩm là "cao nhất" hay "tốt nhất" \
    trừ khi {field} của nó thực sự cao hơn TẤT CẢ sản phẩm còn lại."""