# chat_handler.py
"""
Chat endpoint logic — dùng LangChain ChatOllama + ChatPromptTemplate.
"""

import re
import ollama

from langchain_ollama import ChatOllama
from langchain_core.runnables import RunnableSequence

from util.model_utils import get_ollama_model
from compatibility import build_compatibility_context
from util.utils import format_currency_vietnam, normalize_text
from tool.calculator import CONVERSIONS, convert_if_needed, ALIASES
from unit import get_unit_map
from template.prompt_templates import ADVISOR_TEMPLATE
from util.response_formatter import build_format_hint

# ──────────────────────────────────────────────
# Intent detection config (giữ nguyên từ code cũ)
# ──────────────────────────────────────────────
COMPAT_TRIGGERS = [
    'tương thích', 'lắp được', 'chạy được', 'hợp không',
    'đi cùng', 'đi với', 'vừa không', 'cắm được',
]
CPU_TERMS  = ['cpu', 'vi xử lý', 'i3', 'i5', 'i7', 'i9', 'ryzen']
GPU_TERMS  = ['gpu', 'vga', 'card', 'đồ họa', 'rtx', 'gtx', 'rx']
MAIN_TERMS = ['bo mạch chủ', 'motherboard', 'h610', 'b760', 'z790', 'x670', 'a520']

FIELD_KEYWORD_ALIASES = {
    'tdp':          ['tdp', 'điện năng', 'điện năng tiêu thụ', 'công suất'],
    'xung cơ bản':  ['xung cơ bản', 'base clock'],
    'xung boost':   ['xung boost', 'boost clock'],
    'bộ nhớ':       ['bộ nhớ', 'memory'],
    'socket':       ['socket', 'socket type', 'loại socket'],
}


# ──────────────────────────────────────────────
# LangChain chain — khởi tạo lazy (tránh lỗi khi
# Ollama chưa chạy lúc import)
# ──────────────────────────────────────────────
_chain: RunnableSequence | None = None

def _get_chain() -> RunnableSequence:
    """Trả về chain, tạo mới nếu chưa có."""
    global _chain
    if _chain is None:
        llm = ChatOllama(
            model=get_ollama_model(),
            temperature=0.0,
            top_p=0.1,
        )
        _chain = ADVISOR_TEMPLATE | llm
    return _chain


# ──────────────────────────────────────────────
# Normalise & intent (giữ nguyên từ code cũ)
# ──────────────────────────────────────────────
def _normalize_user_message(user_message: str) -> str:
    return (
        user_message
        .lower()
        .replace("main",          "bo mạch chủ")
        .replace("chip",          "cpu")
        .replace("card đồ họa",   "gpu")
        .replace("vga",           "gpu")
        .replace("đồ họa",        "gpu")
        .replace("điện năng",     "tdp")
        .replace("điện năng tiêu thụ", "tdp")
    )


def _detect_intent(msg_lower: str):
    is_compat = any(w in msg_lower for w in COMPAT_TRIGGERS)
    has_cpu   = any(w in msg_lower for w in CPU_TERMS)
    has_gpu   = any(w in msg_lower for w in GPU_TERMS)
    has_main  = any(w in msg_lower for w in MAIN_TERMS)
    return is_compat, has_cpu, has_gpu, has_main


# ──────────────────────────────────────────────
# Context builders (giữ nguyên từ code cũ)
# ──────────────────────────────────────────────
def _field_relevance_score(field_name: str, msg_lower: str) -> int:
    field_lower = field_name.lower()
    if field_lower in msg_lower:
        return 2
    for alias in FIELD_KEYWORD_ALIASES.get(field_lower, []):
        if alias in msg_lower:
            return 2
    return 0


def _get_category(has_gpu, has_cpu, has_main) -> str | None:
    if has_gpu:   return 'GPU'
    if has_cpu:   return 'CPU'
    if has_main:  return 'MAINBOARD'
    return None


def _build_product_context(user_message: str, category: str | None,
                            matched_items: list) -> str:
    """Build product listing string từ matched_items đã fetch sẵn."""
    if not matched_items or not isinstance(matched_items, list):
        return ""

    msg_lower = user_message.lower()
    requested_unit = None
    for unit in CONVERSIONS.keys():
        if re.search(rf"\b{re.escape(unit.lower())}\b", msg_lower):
            requested_unit = unit
            break
    if not requested_unit:
        for alias, canonical in ALIASES.items():
            if alias.lower() in msg_lower:
                requested_unit = canonical
                break

    lines = ["Danh sách linh kiện thực tế đang có sẵn tại cửa hàng:"]
    for item in matched_items:
        p_format = item.get('price_formatted') or format_currency_vietnam(
            item.get('giá') if 'giá' in item else item.get('price', 0)
        )
        name = item.get('tên') or item.get('name')
        exclude_keys = {
            'category', 'tên', 'name', 'giá', 'price',
            'price_formatted', 'search_text',
        }
        field_entries = []
        current_unit_map = get_unit_map(category)

        for index, (key, val) in enumerate(item.items()):
            if key in exclude_keys or val is None:
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
                    formatted_value = f"{key}: {val} {unit}"
                    conversions = convert_if_needed(val, unit, requested_unit)
                    field_entries.append((
                        _field_relevance_score(key, msg_lower),
                        index, formatted_value, conversions,
                    ))
                else:
                    field_entries.append((
                        _field_relevance_score(key, msg_lower),
                        index, f"{key}: {val}", [],
                    ))
            else:
                field_entries.append((
                    _field_relevance_score(key, msg_lower),
                    index, f"{key}: {val}", [],
                ))

        field_entries.sort(key=lambda x: (-x[0], x[1]))
        extra_parts = []
        for _, _, entry, conversions in field_entries:
            extra_parts.append(entry)
            extra_parts.extend(conversions)

        extra = (' | ' + ' | '.join(extra_parts)) if extra_parts else ''
        lines.append(
            f"- [{item.get('category')}] {name} | Giá: {p_format} VNĐ{extra}"
        )

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────
def handle_chat(user_message: str, knowledge_base,
                compatibility_rules, search_fn) -> dict:

    if knowledge_base is None:
        return {"chatbot_reply": "HỆ THỐNG CHƯA SẴN SÀNG!"}

    # 1. Normalise & detect intent
    user_message_fixed = _normalize_user_message(user_message)
    msg_lower          = normalize_text(user_message_fixed)
    is_compat, has_cpu, has_gpu, has_main = _detect_intent(msg_lower)
    category = _get_category(has_gpu, has_cpu, has_main)

    # 2. Fetch matched items một lần duy nhất (dùng lại cho cả context lẫn formatter)
    matched_items = search_fn(q=user_message, category=category, top_k=4) or []

    # 3. Build compatibility context (nếu có)
    compatibility_context = ""
    if is_compat:
        compatibility_context = build_compatibility_context(
            user_message_fixed, knowledge_base, compatibility_rules, search_fn
        )

    # 4. Build product context (nếu không có compat)
    product_context = ""
    if not compatibility_context:
        product_context = _build_product_context(
            user_message, category, matched_items
        )

    # 5. Nothing found?
    if not compatibility_context and not product_context:
        return {
            "chatbot_reply": (
                "Dạ hiện tại em chưa tìm thấy mã sản phẩm này trong kho. "
                "Bạn cung cấp rõ tên model giúp em nhé!"
            )
        }

    # 6. Chọn context & build format_hint
    context = compatibility_context if compatibility_context else product_context

    # Compat query không cần format hint
    format_hint = build_format_hint(user_message, matched_items) \
                  if not compatibility_context else ""

    # 7. Invoke LangChain chain
    try:
        chain    = _get_chain()
        response = chain.invoke({
            "context":      context,
            "format_hint":  format_hint,   # "" nếu không cần
            "user_message": user_message_fixed,
        })
        return {"chatbot_reply": response.content}

    except Exception as e:
        return {"chatbot_reply": f"❌ Lỗi bộ não AI: {str(e)}"}