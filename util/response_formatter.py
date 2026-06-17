import re
from typing import Optional

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
# Cấu trúc mới: "từ khóa user hỏi": ("tên_cột_trong_DB_của_bạn", "Đơn vị")
NUMERIC_SPEC_SIGNALS = {
    "giá":         ("giá", "VNĐ"),
    "tiền":        ("giá", "VNĐ"),
    "vram":        ("bộ nhớ", "GB"),
    "bộ nhớ":      ("bộ nhớ", "GB"),
    "dung lượng":  ("bộ nhớ", "GB"),
    "xung boost":  ("xung boost", "MHz"),
    "boost clock": ("xung boost", "MHz"),
    "xung cơ bản": ("xung cơ bản", "MHz"),
    "base clock":  ("xung cơ bản", "MHz"),
    "tdp":         ("tdp", "W"),
    "công suất":   ("tdp", "W"),
    "chiều dài":   ("chiều dài", "mm"),
    "dài":         ("chiều dài", "mm"),
}

SPEC_QUERY_TRIGGERS = [
    "bao nhiêu", "là bao nhiêu", "thông số",
    "nhanh nhất", "cao nhất", "thấp nhất", "mạnh nhất", "rẻ nhất", "đắt nhất",
    "xung", "tốc độ", "so sánh", "giá", "tiền"
]

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def detect_spec_field(user_message: str) -> tuple[Optional[str], Optional[str]]:
    """Trả về (tên_cột_DB, unit) dựa trên câu hỏi của user."""
    msg_lower = user_message.lower()
    for trigger_word, (db_key, unit) in NUMERIC_SPEC_SIGNALS.items():
        if trigger_word in msg_lower:
            return db_key, unit
    return None, None

def is_spec_range_query(user_message: str, matched_items: list) -> bool:
    if len(matched_items) <= 1:
        return False
    msg_lower = user_message.lower()
    has_trigger = any(t in msg_lower for t in SPEC_QUERY_TRIGGERS)
    db_key, _ = detect_spec_field(user_message)
    return has_trigger and db_key is not None

def build_range_summary(user_message: str, matched_items: list) -> str:
    db_key, unit = detect_spec_field(user_message)
    if not db_key:
        return ""

    entries = []
    for item in matched_items:
        name = item.get("tên") or item.get("name", "???")
        
        # Duyệt qua các key trong item lấy từ DB
        for key, val in item.items():
            # So sánh chính xác với tên cột DB mà ta đã map ở trên
            if db_key == key.lower().strip():
                numeric_val = None
                
                if isinstance(val, (int, float)):
                    numeric_val = val
                elif isinstance(val, str):
                    # Làm sạch chuỗi để lấy số (VD: "19919760" hoặc "16.0")
                    clean_str = val.replace(".", "").replace(",", "")
                    match = re.search(r'\d+(\.\d+)?', clean_str)
                    if match:
                        numeric_val = float(match.group())

                if numeric_val is not None and numeric_val > 0:
                    entries.append((name, round(numeric_val, 2), unit))
                break 

    if not entries:
        return ""

    values  = [e[1] for e in entries]
    min_val = min(values)
    max_val = max(values)

    # Hàm helper nhỏ để biến 36455760.0 thành "36.455.760" cho AI dễ đọc
    def format_vietnam(val, u):
        if u == "VNĐ":
            return f"{int(val):,}".replace(",", ".")
        return f"{val:g}"

    lines = []
    if min_val != max_val:
        lines.append(
            f"THÔNG TIN BỔ SUNG:\n"
            f"📊 TỔNG HỢP: {db_key.capitalize()} nằm trong khoảng "
            f"{format_vietnam(min_val, unit)} – {format_vietnam(max_val, unit)} {unit}."
        )
    else:
        lines.append(
            f"THÔNG TIN BỔ SUNG:\n"
            f"📊 TỔNG HỢP: Tất cả phiên bản đều có chung mức {db_key} là {format_vietnam(min_val, unit)} {unit}."
        )

    lines.append("Chi tiết (từ cao đến thấp):")
    for name, val, u in sorted(entries, key=lambda x: x[1], reverse=True):
        lines.append(f"  • {name}: {format_vietnam(val, u)} {u}")

    return "\n".join(lines) 