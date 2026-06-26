import re
from typing import Optional, List, Tuple

# ──────────────────────────────────────────────
# Config: trường số + đơn vị tương ứng
# ──────────────────────────────────────────────
NUMERIC_SPEC_SIGNALS = {
    "giá":         ([("giá", "VNĐ")], "VNĐ"),
    "tiền":        ([("giá", "VNĐ")], "VNĐ"),
    "vram":        ([("bộ nhớ", "GB")], "GB"),
    "bộ nhớ":      ([("bộ nhớ", "GB")], "GB"),
    "dung lượng":  ([("bộ nhớ", "GB")], "GB"),
    "xung boost":  ([("xung boost", "MHz")], "MHz"),
    "boost clock": ([("xung boost", "MHz")], "MHz"),
    "xung cơ bản": ([("xung cơ bản", "MHz")], "MHz"),
    "base clock":  ([("xung cơ bản", "MHz")], "MHz"),
    "tdp":         ([("tdp", "W")], "W"),
    "công suất":   ([("tdp", "W")], "W"),
    "chiều dài":   ([("chiều dài", "mm")], "mm"),
    "dài":         ([("chiều dài", "mm")], "mm"),
    "xung":        ([("xung cơ bản", "MHz"), ("xung boost", "MHz")], "MHz"),
    "tốc độ":      ([("xung cơ bản", "MHz"), ("xung boost", "MHz")], "MHz"),
}

SPEC_QUERY_TRIGGERS = [
    "bao nhiêu", "là bao nhiêu", "thông số",
    "nhanh nhất", "cao nhất", "thấp nhất", "mạnh nhất", "rẻ nhất", "đắt nhất",
    "xung", "tốc độ", "so sánh", "giá", "tiền",
]


# ──────────────────────────────────────────────
# Phát hiện trường số được hỏi
# ──────────────────────────────────────────────
def detect_spec_fields(user_message: str) -> Tuple[List[Tuple[str, str]], Optional[str]]:
    """Trả về danh sách [(tên_cột, unit), ...] và unit tổng quát."""
    msg_lower = user_message.lower()
    for trigger_word, (target_fields, unit) in NUMERIC_SPEC_SIGNALS.items():
        if trigger_word in msg_lower:
            return target_fields, unit
    return [], None


def is_spec_range_query(user_message: str, matched_items: list) -> bool:
    if len(matched_items) <= 1:
        return False
    msg_lower = user_message.lower()
    has_trigger = any(t in msg_lower for t in SPEC_QUERY_TRIGGERS)
    target_fields, _ = detect_spec_fields(user_message)
    return has_trigger and len(target_fields) > 0


# ──────────────────────────────────────────────
# Phát hiện điều kiện khoảng giá trong câu hỏi
# ──────────────────────────────────────────────
def parse_price_range_vnd(user_message: str) -> Optional[Tuple[float, float]]:
    """
    Phát hiện điều kiện khoảng giá trong câu hỏi.
    Trả về (min_vnd, max_vnd) hoặc None nếu không có điều kiện giá.
    """
    msg = user_message.lower()

    m = re.search(r'(?:từ\s*)?(\d+(?:[.,]\d+)?)\s*(?:đến|tới|-)\s*(\d+(?:[.,]\d+)?)\s*tri[eệ]u', msg)
    if m:
        lo = float(m.group(1).replace(",", "."))
        hi = float(m.group(2).replace(",", "."))
        return lo * 1_000_000, hi * 1_000_000

    m = re.search(r'dưới\s*(\d+(?:[.,]\d+)?)\s*tri[eệ]u', msg)
    if m:
        hi = float(m.group(1).replace(",", "."))
        return 0.0, hi * 1_000_000

    m = re.search(r'trên\s*(\d+(?:[.,]\d+)?)\s*tri[eệ]u', msg)
    if m:
        lo = float(m.group(1).replace(",", "."))
        return lo * 1_000_000, float("inf")

    # Bắt "khoảng/tầm/cỡ X triệu" -> lấy biên độ +/- 20%
    m = re.search(r'(?:khoảng|tầm|cỡ|mức|quanh)\s*(?:giá\s*)?(\d+(?:[.,]\d+)?)\s*tri[eệ]u', msg)
    if m:
        val = float(m.group(1).replace(",", "."))
        lo = max(0.0, val * 0.8)
        hi = val * 1.2
        return lo * 1_000_000, hi * 1_000_000
        
    # Bắt "giá X triệu" (chính xác mức giá, lấy +/- 10% bù trừ)
    m = re.search(r'giá\s*(\d+(?:[.,]\d+)?)\s*tri[eệ]u', msg)
    if m:
        val = float(m.group(1).replace(",", "."))
        lo = max(0.0, val * 0.9)
        hi = val * 1.1
        return lo * 1_000_000, hi * 1_000_000

    return None


# ──────────────────────────────────────────────
# Build summary cho format_hint — KHÔNG bỏ qua sản phẩm thiếu data,
# ghi nhận rõ ràng để LLM không tự suy luận thay
# ──────────────────────────────────────────────
def build_range_summary(user_message: str, matched_items: list) -> str:
    target_fields, unit = detect_spec_fields(user_message)
    if not target_fields:
        return ""

    entries = []
    missing_names = []

    for item in matched_items:
        name = item.get("tên") or item.get("name", "???")
        hit = False
        for db_key, f_unit in target_fields:
            for key, val in item.items():
                if db_key != key.lower().strip():
                    continue
                numeric_val = None
                if isinstance(val, (int, float)):
                    numeric_val = val
                elif isinstance(val, str):
                    clean_str = val.replace(".", "").replace(",", "")
                    m = re.search(r'\d+(\.\d+)?', clean_str)
                    if m:
                        numeric_val = float(m.group())

                if numeric_val is not None and numeric_val > 0:
                    label = f" ({db_key})" if len(target_fields) > 1 else ""
                    entries.append((f"{name}{label}", round(numeric_val, 2)))
                    hit = True
                break
        if not hit:
            missing_names.append(name)

    if not entries:
        return ""

    values = [e[1] for e in entries]
    min_val, max_val = min(values), max(values)

    def format_vietnam(val, u):
        if u == "VNĐ":
            return f"{int(val):,}".replace(",", ".")
        return f"{val:g}"

    lines = ["THÔNG TIN BỔ SUNG TỪ HỆ THỐNG (đã tính toán sẵn, KHÔNG tự suy luận thêm):"]
    if min_val != max_val:
        lines.append(
            f"📊 TỔNG HỢP: dao động từ {format_vietnam(min_val, unit)} đến {format_vietnam(max_val, unit)} {unit}."
        )
    else:
        lines.append(f"📊 TỔNG HỢP: tất cả ở mức {format_vietnam(min_val, unit)} {unit}.")

    lines.append("Danh sách CÓ dữ liệu:")
    for name, val in sorted(entries, key=lambda x: x[1], reverse=True):
        lines.append(f"  • {name}: {format_vietnam(val, unit)} {unit}")

    if missing_names:
        lines.append("Danh sách CHƯA CÓ dữ liệu cho thông số này (không được tự suy ra giá trị):")
        for name in missing_names:
            lines.append(f"  • {name}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Hậu xử lý — chặn cụm từ máy móc / lộ reasoning còn sót lại
# ──────────────────────────────────────────────
def word_filter(reply: str) -> str:
    # lọc không giải thích leak system promt
    paragraph_cutoff_pattern = re.compile(
        r'\b(giải thích|lý do)\s*:', re.IGNORECASE
    )
    m = paragraph_cutoff_pattern.search(reply)
    if m:
        reply = reply[:m.start()]

    forbidden_pattern = r'(dựa trên|theo)\s+(thông tin|dữ liệu)\s*(được cung cấp|trên|ở trên)?'
    reply = re.sub(forbidden_pattern, '', reply, flags=re.IGNORECASE)

    reply = re.sub(r'câu trả lời cho\s*["\']?.*?["\']?\s*là\s*:?\s*',
                    '', reply, flags=re.IGNORECASE)

    reply = re.sub(r'vì vậy|vì thế|do đó', '', reply, flags=re.IGNORECASE)

    reply = re.sub(r'\[GỢI Ý LINH KIỆN TƯƠNG THÍCH VỚI .*?\]', '', reply).strip()
    # Xóa bớt khoảng trắng thừa hoặc dấu hai chấm thừa nếu có
    reply = reply.replace("ạ: \n", "ạ:\n").replace("ạ: \n\n", "ạ:\n\n")

    internal_note_pattern = r'[^.]*\b(đã (được )?tính toán sẵn|không cần (phải )?suy luận thêm)\b[^.]*\.?'
    reply = re.sub(internal_note_pattern, '', reply, flags=re.IGNORECASE)

    # ⭐ Chặn meta-commentary về việc tuân thủ instruction / tên label nội bộ
    meta_commentary_pattern = (
        r'[^.]*\b('
        r'dữ liệu thực tế dành cho bạn|'
        r'không cần (phải )?sử dụng dữ liệu|'
        r'đã đủ để trả lời|'
        r'trả lời (một cách )?(chính xác và )?đầy đủ'
        r'tuân thủ( các)? quy tắc|'       
        r'phong cách trả lời|'            
        r'cụm từ máy móc|'                  
        r'danh sách liệt kê'
        r')\b[^.]*\.?'
    )
    reply = re.sub(meta_commentary_pattern, '', reply, flags=re.IGNORECASE)

    robot_phrases = [
        "Trong danh sách sản phẩm", "Vì vậy,", "Tuy nhiên,",
        "Lý do:", "Do đó,", "Có thể là",
    ]
    for phrase in robot_phrases:
        reply = re.compile(re.escape(phrase), re.IGNORECASE).sub('', reply)

    reply = re.sub(r'^\s*,\s*', '', reply).strip()
    reply = re.sub(r'[ \t]+', ' ', reply)

    if not reply.startswith("Dạ"):
        reply = "Dạ, " + reply

    return reply