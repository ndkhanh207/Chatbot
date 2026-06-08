"""Chat endpoint logic – extracted from ``main.py``.

This module contains all the business logic for the ``/chat`` endpoint so that
``main.py`` only needs to wire up the FastAPI routes and lifespan.  Keeping the
logic separate makes it easier to unit‑test and maintain.
"""

import ollama
from model_utils import get_ollama_model
from compatibility import build_compatibility_context
from utils import format_currency_vietnam, normalize_text


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
        .replace("main", "bo mạch chủ")
        .replace("chip", "cpu")
        .replace("card đồ họa", "gpu")
        .replace("vga", "gpu")
        .replace("đồ họa", "gpu")
    )


def _detect_intent(msg_lower: str):
    """Return a tuple ``(is_compat_query, has_cpu, has_gpu, has_main)``."""
    is_compat = any(w in msg_lower for w in COMPAT_TRIGGERS)
    has_cpu = any(w in msg_lower for w in CPU_TERMS)
    has_gpu = any(w in msg_lower for w in GPU_TERMS)
    has_main = any(w in msg_lower for w in MAIN_TERMS)
    return is_compat, has_cpu, has_gpu, has_main


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

    lines = ["Danh sách linh kiện thực tế đang có sẵn tại cửa hàng:"]
    for item in matched_items:
        p_format = item.get('price_formatted') or format_currency_vietnam(
            item.get('giá') if 'giá' in item else item.get('price', 0)
        )
        name = item.get('tên') or item.get('name')
        # Tự động thêm các thông tin chi tiết còn lại (không cần liệt kê từng loại)
        # Bỏ qua các trường đã hiển thị và các trường không có giá trị.
        exclude_keys = {'category', 'tên', 'name', 'giá', 'price', 'price_formatted'}
        extra_parts = []
        # -----------------------------------------------------------------
        # Unit handling – a per‑category mapping with a fallback "default"
        # -----------------------------------------------------------------
        # The outer dict is keyed by product category (uppercase strings as
        # used in the search results).  Each inner dict maps a lower‑cased field
        # name to its unit.  The special "default" entry is used when a field
        # does not have a category‑specific override.
        UNIT_MAP = {
            "default": {
                'ram tối đa': 'GB',
                'giá': 'VND',
                'tdp': 'W',
                'xung cơ bản': 'GHz',   # CPU default
                'xung boost': 'GHz',
                'kich thước': 'mm',
            },
            "GPU": {
                # GPU clock speeds are expressed in megahertz
                'xung cơ bản': 'MHz',
                'xung boost': 'MHz',
            },
            # Additional categories (e.g., "CPU", "MAINBOARD") can be added
            # here if they need different units for the same field.
        }
        # Determine which unit map to use for the current category.  If the
        # category does not have a specific override, fall back to the default
        # mapping.
        current_unit_map = UNIT_MAP.get(category, UNIT_MAP["default"])

        for key, val in item.items():
            if key in exclude_keys:
                continue
            if val is None:
                continue
            # Pandas NaN check
            try:
                import pandas as pd
                if pd.isna(val):
                    continue
            except Exception:
                pass
            if str(val).strip() == "" or (isinstance(val, (int, float)) and val == 0):
                continue
            # Apply unit suffix if the field is known and the value is numeric
            lower_key = key.lower()
            if lower_key in current_unit_map:
                # If the value already contains a unit (string), keep it as‑is
                if isinstance(val, (int, float)):
                    extra_parts.append(f"{key}: {val} {current_unit_map[lower_key]}")
                else:
                    extra_parts.append(f"{key}: {val}")
                continue
            # Default handling – just show key and value
            extra_parts.append(f"{key}: {val}")
        extra = ''
        if extra_parts:
            extra = ' | ' + ' | '.join(extra_parts)
        lines.append(f"- [{item.get('category')}] {name} | Giá: {p_format} VNĐ{extra}")

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
5. TUYỆT ĐỐI KHÔNG LẶP LẠI: Không được nhắc lại nhãn "DỮ LIỆU THỰC TẾ", "[TRUTH CONTEXT]" hay bất kỳ nhãn cấu trúc nào trong câu trả lời. Chỉ trả lời trực tiếp bằng ngôn ngữ tự nhiên.
"""


def _build_context_message(context: str) -> str:
    """Build a separate context block that will be sent as its own message.

    Keeping the context in a dedicated message (instead of embedding it inside
    the system prompt) helps small LLMs distinguish between *instructions* and
    *data*, reducing the chance that they leak structural labels like
    ``[TRUTH CONTEXT]`` into their replies.
    """
    return f"""DỮ LIỆU THỰC TẾ (chỉ sử dụng thông tin dưới đây để trả lời, không nhắc lại nhãn này):

{context}"""


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
        return {"chatbot_reply": response['message']['content']}
    except Exception as e:
        return {"chatbot_reply": f"❌ Lỗi bộ não AI: {str(e)}"}
