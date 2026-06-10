"""Chat endpoint logic – extracted from ``main.py``.

This module contains all the business logic for the ``/chat`` endpoint so that
``main.py`` only needs to wire up the FastAPI routes and lifespan.  Keeping the
logic separate makes it easier to unit‑test and maintain.
"""

import re
import ollama
from model_utils import get_ollama_model
from compatibility import build_compatibility_context
from utils import format_currency_vietnam, normalize_text
from tool.calculator import auto_convert_context_value
from unit_config import get_unit_map


# ──────────────────────────────────────────────
# Intent detection helpers
# ──────────────────────────────────────────────

COMPAT_TRIGGERS = [
    'tương thích', 'lắp được', 'chạy được', 'hợp không',
    'đi cùng', 'đi với', 'vừa không', 'cắm được',
]
CPU_TERMS = ['cpu', 'vi xử lý', 'i3', 'i5', 'i7', 'i9', 'ryzen']
GPU_TERMS = ['gpu', 'vga', 'card', 'đồ họa', 'rtx', 'gtx', 'rx']
MAIN_TERMS = ['bo mạch chủ', 'motherboard', 'h610', 'b760', 'z790', 'x670', 'a520']


def _normalize_user_message(user_message: str) -> str:
    """Chuẩn hóa từ lóng tiếng Việt trong câu hỏi của người dùng."""
    return (
        user_message
        .lower()
        # FIX: "main" → "bo mạch chủ" (not "bo mạch chủboard" — no stray "board" suffix)
        .replace("mainboard", "bo mạch chủ")
        .replace("main", "bo mạch chủ")
        .replace("chip", "cpu")
        .replace("card đồ họa", "gpu")
        .replace("vga", "gpu")
        .replace("đồ họa", "gpu")
        .replace("điện năng tiêu thụ", "tdp")
        .replace("điện năng", "tdp")
    )


def _detect_intent(msg_lower: str):
    """Return a tuple ``(is_compat_query, has_cpu, has_gpu, has_main)``."""
    is_compat = any(w in msg_lower for w in COMPAT_TRIGGERS)
    has_cpu = any(w in msg_lower for w in CPU_TERMS)
    has_gpu = any(w in msg_lower for w in GPU_TERMS)
    has_main = any(w in msg_lower for w in MAIN_TERMS)
    return is_compat, has_cpu, has_gpu, has_main


# ──────────────────────────────────────────────
# Reply post-processor  (safety net for rule violations)
# ──────────────────────────────────────────────

# Phrases that leak the internal data-layer structure (Rule 5)
_STRUCTURAL_LEAK_PATTERNS = [
    r'dựa trên thông tin (được )?cung cấp[,.]?',
    r'\[?dữ liệu thực tế\]?',
    r'\[?truth context\]?',
    r'theo (dữ liệu|thông tin) (hệ thống|được cung cấp)[,.]?',
    r'trong (dữ liệu|thông tin) (đã )?cung cấp[,.]?',
]

# Phrases that make forbidden price comparisons (Rule 8)
_PRICE_COMPARISON_PATTERNS = [
    r'(giá )?(cao|đắt|mắc) nhất( trong danh sách| hiện có| hiện tại)?',
    r'(giá )?(rẻ|thấp|thấp hơn|cao hơn) nhất( trong danh sách| hiện có| hiện tại)?',
    r'so với các .{0,30}(khác|còn lại)',
    r'(cao|thấp|rẻ|đắt) hơn (các )?(sản phẩm|bo mạch|cpu|gpu)',
]

# Analysis/reasoning blocks that violate Rule 9
_ANALYSIS_BLOCK_PATTERNS = [
    r'\*?\*?lý do\*?\*?\s*[:\-–].*',          # "Lý do: ..." (possibly with **)
    r'\*?\*?phân tích\*?\*?\s*[:\-–].*',
    r'- \*?\*?(giá cao nhất|lý do|vì vậy)\*?\*?.*',
]


def _sanitise_reply(text: str) -> str:
    """Remove rule-violating patterns from the LLM reply.

    This acts as a deterministic safety net so that instruction-following
    failures in the local LLM do not reach the end user.
    """
    # Work line-by-line for block-level patterns
    lines = text.splitlines()
    cleaned_lines = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue

        lower = line.lower()

        # Drop analysis block headers and their content lines
        if re.search(r'^\s*\*?\*?(lý do|phân tích)\*?\*?\s*[:\-–]', lower):
            skip_next = False  # the content is on the same line; handled below
            line = re.sub(r'\*?\*?(lý do|phân tích)\*?\*?\s*[:\-–].*', '', line, flags=re.IGNORECASE).strip()
            if not line:
                continue

        cleaned_lines.append(line)

    text = '\n'.join(cleaned_lines)

    # Apply inline substitutions
    flags = re.IGNORECASE | re.DOTALL

    for pattern in _STRUCTURAL_LEAK_PATTERNS:
        text = re.sub(pattern, '', text, flags=flags)

    for pattern in _PRICE_COMPARISON_PATTERNS:
        text = re.sub(pattern, '', text, flags=flags)

    for pattern in _ANALYSIS_BLOCK_PATTERNS:
        text = re.sub(pattern, '', text, flags=flags)

    # Clean up any double-spaces or orphaned punctuation left behind
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


# ──────────────────────────────────────────────
# Context builders
# ──────────────────────────────────────────────

def _build_product_context(user_message: str, has_cpu: bool, has_gpu: bool,
                           has_main: bool, search_fn) -> str:
    """Build a product‑listing context string for non‑compatibility queries."""
    category = None
    if has_gpu:
        category = 'GPU'
    elif has_cpu:
        category = 'CPU'
    elif has_main:
        category = 'MAINBOARD'

    matched_items = search_fn(q=user_message, category=category, top_k=4)
    if not matched_items or not isinstance(matched_items, list):
        return ""

    # ── Fallback sentinel: hybrid_search found NO products in the price range ──
    first = matched_items[0]
    if first.get('is_fallback') and first.get('fallback_target_price') is not None:
        target = first['fallback_target_price']
        mode   = first.get('fallback_mode', 'less')
        cat_label = first.get('category') or category or 'sản phẩm'

        if mode == 'less':
            range_desc = f"dưới {format_currency_vietnam(target)} VNĐ"
        elif mode == 'greater':
            range_desc = f"trên {format_currency_vietnam(target)} VNĐ"
        else:
            range_desc = f"tầm {format_currency_vietnam(target)} VNĐ"

        # Return a plain-language instruction; no substitute products are listed.
        return (
            f"THÔNG BÁO HỆ THỐNG: Trong kho KHÔNG CÓ {cat_label} nào có giá {range_desc}.\n"
            f"Hãy thông báo thành thật với khách hàng rằng hiện tại không có sản phẩm nào "
            f"trong khoảng giá đó. Không gợi ý sản phẩm thay thế."
        )

    lines = ["Danh sách linh kiện thực tế đang có sẵn tại cửa hàng:"]

    for item in matched_items:
        p_format = item.get('price_formatted') or format_currency_vietnam(
            item.get('giá') if 'giá' in item else item.get('price', 0)
        )
        name = item.get('tên') or item.get('name')

        exclude_keys = {
            'category', 'tên', 'name', 'giá', 'price', 'price_formatted',
            'search_text', 'is_fallback',
        }
        extra_parts = []
        current_unit_map = get_unit_map(category)

        for key, val in item.items():
            if key in exclude_keys:
                continue
            if val is None:
                continue
            try:
                import pandas as pd
                if pd.isna(val):
                    continue
            except Exception:
                pass
            if str(val).strip() == "" or (isinstance(val, (int, float)) and val == 0):
                continue

            lower_key = key.lower()
            if lower_key in current_unit_map:
                unit = current_unit_map[lower_key]
                if isinstance(val, (int, float)):
                    extra_parts.append(f"{key}: {val} {unit}")
                    conversions = auto_convert_context_value(val, unit)
                    extra_parts.extend(conversions)
                else:
                    extra_parts.append(f"{key}: {val}")
                continue

            extra_parts.append(f"{key}: {val}")

        extra = ''
        if extra_parts:
            extra = ' | ' + ' | '.join(extra_parts)
        lines.append(f"- [{item.get('category')}] {name} | Giá thực tế: {p_format} VNĐ{extra}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# System prompt builder
# ──────────────────────────────────────────────

_SYSTEM_PROMPT = """Bạn là trợ lý ảo AI chuyên tư vấn linh kiện máy tính.
Nhiệm vụ của bạn là sử dụng DUY NHẤT các thông tin được cung cấp trong phần "DỮ LIỆU THỰC TẾ" bên dưới để trả lời câu hỏi của khách hàng.

[QUY TẮC TỐI QUAN TRỌNG]
1. TUYỆT ĐỐI KHÔNG BỊA ĐẶT: Không tự ý thêm thắt tên sản phẩm, giá tiền, hay thông số nếu không xuất hiện trong "DỮ LIỆU THỰC TẾ".
2. NGUYÊN BẢN DỮ LIỆU: Giữ nguyên tên linh kiện, mã sản phẩm và giá tiền y như trong dữ liệu gốc.
3. TUYỆT ĐỐI KHÔNG CÃI HỆ THỐNG: Nếu "DỮ LIỆU THỰC TẾ" ghi là "TƯƠNG THÍCH HOÀN HẢO", bạn phải khẳng định 100% là tương thích. Nếu ghi "KHÔNG TƯƠNG THÍCH", phải cảnh báo khách hàng ngay lập tức.
4. Trả lời lịch sự, ngắn gọn và xưng hô thân thiện với người dùng.
5. TUYỆT ĐỐI KHÔNG LẶP LẠI NHÃN CẤU TRÚC: Không được nhắc lại "DỮ LIỆU THỰC TẾ", "[TRUTH CONTEXT]", "dựa trên thông tin được cung cấp", "theo dữ liệu hệ thống", hay bất kỳ nhãn nội bộ nào. Trả lời thẳng bằng ngôn ngữ tự nhiên, như thể bạn tự biết thông tin này.
6. CHUYỂN ĐỔI ĐƠN VỊ: Dữ liệu thực tế đã bao gồm các chuyển đổi đơn vị sẵn (ví dụ: "64 GB = 65536 MB"). Hãy SỬ DỤNG trực tiếp các giá trị chuyển đổi này trong câu trả lời.
7. ĐỐI CHIẾU GIÁ THỰC TẾ: Nếu trong dữ liệu xuất hiện dòng "[THÔNG BÁO HỆ THỐNG]: Trong kho KHÔNG CÓ sản phẩm nào...", bạn phải thông báo thành thật cho khách là không có sản phẩm nào đạt mức giá đó. Sau đó, hãy trân trọng giới thiệu các dòng sản phẩm thay thế được liệt kê.
8. KHÔNG TỰ SO SÁNH GIÁ: Tuyệt đối không dùng các từ như "cao hơn", "thấp hơn", "cao nhất", "rẻ nhất", "đắt nhất", "so với các sản phẩm khác" để so sánh sản phẩm với nhau.
9. CHỈ LIỆT KÊ GIÁ: Nhiệm vụ của bạn chỉ là thông báo tên và giá tiền của các sản phẩm có trong danh sách. Không giải thích, không phân tích, không lý do, không bullet point "Lý do:".

[VÍ DỤ TRẢ LỜI ĐÚNG]
Câu hỏi: "Bo mạch chủ nào giá cao nhất?"
✅ ĐÚNG: "Dạ, bo mạch chủ có giá cao nhất hiện tại là Gigabyte Z890 AI TOP với giá 21.589.464 VNĐ ạ. Bạn có muốn biết thêm thông số không?"
❌ SAI: "Dựa trên thông tin được cung cấp, bo mạch chủ có giá cao nhất là ... Lý do: - Giá cao nhất: ... - Thông tin chi tiết: ..."
"""


def _build_context_message(context: str) -> str:
    """Build a context block sent as a separate system message.

    Keeping context separate from the instruction system prompt helps small
    LLMs distinguish between *rules* and *data*, and repeating the most
    critical rules here reinforces them close to the data where they matter.
    """
    # Re-state the three most commonly violated rules right before the data
    # so they are in the model's immediate context window when it reads the
    # product list.
    reinforcement = (
        "NHẮC LẠI QUY TẮC QUAN TRỌNG NHẤT:\n"
        "- KHÔNG dùng cụm 'dựa trên thông tin', 'theo dữ liệu', hay nhắc lại nhãn nội bộ.\n"
        "- KHÔNG so sánh giá (cao nhất / rẻ nhất / cao hơn / thấp hơn).\n"
        "- KHÔNG viết mục 'Lý do:' hay phân tích. Chỉ liệt kê tên + giá.\n"
    )
    return (
        f"{reinforcement}\n"
        f"DỮ LIỆU THỰC TẾ (chỉ sử dụng thông tin dưới đây để trả lời, "
        f"không nhắc lại nhãn này):\n\n{context}"
    )


# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────

def handle_chat(user_message: str, knowledge_base, compatibility_rules,
                search_fn) -> dict:
    """Process a chat request and return ``{"chatbot_reply": ...}``.

    Parameters
    ----------
    user_message : str
        Raw message from the user.
    knowledge_base : pandas.DataFrame
        The full product knowledge base (may be ``None`` if startup failed).
    compatibility_rules : pandas.DataFrame
        Compatibility rules loaded from CSV.
    search_fn : callable
        A function with the same signature as the ``/test-knowledge-base``
        endpoint – ``search_fn(q, category, top_k)`` – used to retrieve
        matching products.
    """
    if knowledge_base is None:
        return {"chatbot_reply": "HỆ THỐNG CHƯA SẴN SÀNG!"}

    # 1. Normalise & detect intent
    user_message_fixed = _normalize_user_message(user_message)
    msg_lower = normalize_text(user_message_fixed)
    is_compat, has_cpu, has_gpu, has_main = _detect_intent(msg_lower)

    # 2. Build compatibility context (if applicable)
    compatibility_context = ""
    if is_compat:
        compatibility_context = build_compatibility_context(
            user_message_fixed, knowledge_base, compatibility_rules, search_fn
        )

    # 3. Build product context (fallback when no compatibility check)
    product_context = ""
    if not compatibility_context:
        product_context = _build_product_context(
            user_message, has_cpu, has_gpu, has_main, search_fn
        )

    # 4. Nothing found?
    if not compatibility_context and not product_context:
        return {
            "chatbot_reply": (
                "Dạ hiện tại em chưa tìm thấy mã sản phẩm này trong kho. "
                "Bạn cung cấp rõ tên model giúp em nhé!"
            )
        }

    # 5. Build prompt & call LLM
    context = compatibility_context if compatibility_context else product_context
    context_message = _build_context_message(context)

    try:
        response = ollama.chat(
            model=get_ollama_model(),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "system", "content": context_message},
                {"role": "user", "content": user_message_fixed},
            ],
            options={"temperature": 0.0, "top_p": 0.1},
        )
        raw_reply = response['message']['content']

        # 6. Post-process: strip any rule-violating phrases the LLM still produced
        clean_reply = _sanitise_reply(raw_reply)

        return {"chatbot_reply": clean_reply}
    except Exception as e:
        return {"chatbot_reply": f"❌ Lỗi bộ não AI: {str(e)}"}