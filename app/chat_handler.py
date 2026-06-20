"""
Chat endpoint logic — dùng LangChain ChatOllama + ChatPromptTemplate.
"""

import re
from typing import Optional

from langchain_ollama import ChatOllama
from langchain_core.runnables import RunnableSequence

from util.model_utils import get_ollama_model
from util.utils import normalize_text
from app.compact.pricing import format_currency_vietnam
from tool.calculator import CONVERSIONS, convert_if_needed, ALIASES
from util.unit import get_unit_map
from template.prompt_templates import ADVISOR_TEMPLATE, COMPAT_CHECK_TEMPLATE, SUGGESTION_TEMPLATE, REFORMULATE_TEMPLATE
from util.response_formatter import build_range_summary, parse_price_range_vnd, world_filter
from memory.memory_store import get_trimmed_history, save_message
from app.search_engine import hybrid_search
from app.compact.compatibility import (
    build_compatibility_context, build_suggestion_context,
    is_compatibility_query, parse_compat_intent,
    CPU_TERMS, GPU_TERMS, MAIN_TERMS,
)
from app.compact.price_calculator import (
    build_price_calculation_context, is_price_calculation_query,
)

# ──────────────────────────────────────────────
# Field alias config (không liên quan compat — giữ riêng ở đây)
# ──────────────────────────────────────────────
FIELD_KEYWORD_ALIASES = {
    'tdp':          ['tdp', 'điện năng', 'điện năng tiêu thụ', 'công suất'],
    'xung cơ bản':  ['xung cơ bản', 'base clock'],
    'xung boost':   ['xung boost', 'boost clock'],
    'bộ nhớ':       ['bộ nhớ', 'memory'],
    'socket':       ['socket', 'socket type', 'loại socket'],
}

_reformulate_chain = None
_chain: RunnableSequence | None = None
_compat_check_chain = None
_suggestion_chain = None

def _get_llm() -> ChatOllama:
    return ChatOllama(
        model=get_ollama_model(),
        temperature=0.1,
        request_timeout=30,
        top_p=0.1,
    )


def _get_chain() -> RunnableSequence:
    global _chain
    if _chain is None:
        _chain = ADVISOR_TEMPLATE | _get_llm()
    return _chain


def _get_compat_check_chain() -> RunnableSequence:
    global _compat_check_chain
    if _compat_check_chain is None:
        from template.prompt_templates import COMPAT_CHECK_TEMPLATE
        _compat_check_chain = COMPAT_CHECK_TEMPLATE | _get_llm()
    return _compat_check_chain

def _get_suggestion_chain() -> RunnableSequence:
    global _suggestion_chain
    if _suggestion_chain is None:
        from template.prompt_templates import SUGGESTION_TEMPLATE
        _suggestion_chain = SUGGESTION_TEMPLATE | _get_llm()
    return _suggestion_chain


def _get_reformulate_chain():
    global _reformulate_chain
    if _reformulate_chain is None:
        _reformulate_chain = REFORMULATE_TEMPLATE | ChatOllama(
            model=get_ollama_model(), temperature=0.1, request_timeout=30
        )
    return _reformulate_chain


def _looks_like_full_answer(text: str) -> bool:
    """Phát hiện khi reformulate chain trả lời luôn thay vì chỉ viết lại câu hỏi —
    dấu hiệu: có giá tiền, lời chào, hoặc câu khẳng định kiểu trả lời."""
    markers = ['vnđ', 'giá khoảng', 'tôi sẽ đề xuất', 'dạ,', 'bạn nên chọn']
    return any(m in text.lower() for m in markers)


def _reformulate_query(user_message: str, chat_history: list) -> str:
    if not chat_history:
        return user_message
    specific_terms = ['rtx', 'gtx', 'rx', 'i3', 'i5', 'i7', 'i9',
                      'ryzen', 'b760', 'z790', 'x670', 'h610']
    if any(t in user_message.lower() for t in specific_terms):
        return user_message
    try:
        # Chuyển đổi chat_history từ object sang chuỗi văn bản thuần túy
        # để tránh Qwen 1.5B bị kích hoạt chế độ roleplay (nhầm tưởng là hội thoại trực tiếp)
        history_str = ""
        for msg in chat_history:
            if getattr(msg, "type", "") == "human":
                history_str += f"Khách: {msg.content}\n"
            elif getattr(msg, "type", "") == "ai":
                history_str += f"Bot: {msg.content}\n"

        response = _get_reformulate_chain().invoke({
            "user_message": user_message,
            "chat_history_str": history_str,
        })
        reformulated = response.content.strip()

        # Guard: nếu output trông như câu trả lời hoàn chỉnh (hallucination)
        # thay vì câu hỏi viết lại, bỏ qua, dùng query gốc.
        if _looks_like_full_answer(reformulated) or len(reformulated) > max(100, len(user_message) * 3):
            print(f"[REFORMULATE] Bị loại bỏ vì giống câu trả lời. LLM đã sinh ra:\n'{reformulated}'")
            return user_message

        print(f"[REFORMULATE] '{user_message}' → '{reformulated}'")
        return reformulated
    except Exception as e:
        print(f"[REFORMULATE] Lỗi, dùng query gốc: {e}")
        return user_message


# ──────────────────────────────────────────────
# Normalise & intent
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
    
OWNERSHIP_HINTS = ['tôi có', 'tôi đã có', 'sẵn có', 'đang dùng', 'đang có']

def _has_ownership_signal(msg_lower: str) -> bool:
    return any(h in msg_lower for h in OWNERSHIP_HINTS)

def _detect_intent(msg_lower: str):
    is_compat = is_compatibility_query(msg_lower)   # dùng list đầy đủ từ compat.py
    has_cpu   = any(w in msg_lower for w in CPU_TERMS)
    has_gpu   = any(w in msg_lower for w in GPU_TERMS)
    has_main  = any(w in msg_lower for w in MAIN_TERMS)
    return is_compat, has_cpu, has_gpu, has_main


def _get_category(msg_lower: str) -> str | None:
    first_idx = float('inf')
    best_cat = None
    
    for cat_name, terms in [('MAINBOARD', MAIN_TERMS), ('GPU', GPU_TERMS), ('CPU', CPU_TERMS)]:
        for term in terms:
            idx = msg_lower.find(term)
            if idx != -1 and idx < first_idx:
                first_idx = idx
                best_cat = cat_name
                
    return best_cat


def _detect_brand(msg_lower: str) -> Optional[str]:
    """Trả về từ khóa khớp với cột 'chipset' của GPU trong dataset thực tế."""
    if "nvidia" in msg_lower or "rtx" in msg_lower or "gtx" in msg_lower:
        return "geforce"
    if "amd" in msg_lower or "radeon" in msg_lower or " rx " in msg_lower:
        return "radeon"
    return None


# ──────────────────────────────────────────────
# Context builders
# ──────────────────────────────────────────────
def _field_relevance_score(field_name: str, msg_lower: str) -> int:
    field_lower = field_name.lower()
    if field_lower in msg_lower:
        return 2
    for alias in FIELD_KEYWORD_ALIASES.get(field_lower, []):
        if alias in msg_lower:
            return 2
    return 0


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

    wants_all_specs = any(w in msg_lower for w in ["thông số", "chi tiết", "cấu hình", "specs", "đặc điểm", "toàn bộ"])

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
        for score, _, entry, conversions in field_entries:
            if wants_all_specs or score > 0:
                extra_parts.append(entry)
                extra_parts.extend(conversions)

        extra = (' | ' + ' | '.join(extra_parts)) if extra_parts else ''
        lines.append(
            f"- [{item.get('category')}] {name} | Giá: {p_format} VNĐ{extra}"
        )

    return "\n".join(lines)


def _filter_knowledge_base_by_price(knowledge_base, category, lo, hi,
                                     brand=None, top_k=10):
    """
    Lọc TRỰC TIẾP trên toàn bộ knowledge_base (DataFrame) theo khoảng giá,
    không phụ thuộc vào kết quả semantic search top_k.
    Trả về (list[dict], total_count).
    """
    df = knowledge_base
    price_col = "giá" if "giá" in df.columns else "price"

    mask = (df[price_col] >= lo) & (df[price_col] <= hi)
    if category and "category" in df.columns:
        mask &= (df["category"] == category)

    if brand:
        search_col = "chipset" if "chipset" in df.columns else (
            "tên" if "tên" in df.columns else "name"
        )
        mask &= df[search_col].str.contains(brand, case=False, na=False)

    full_match = df[mask]
    if full_match.empty:
        return [], 0

    total_count = len(full_match)
    sorted_df = full_match.sort_values(by=price_col)

    if total_count <= top_k:
        sample = sorted_df
    else:
        step = max(1, total_count // top_k)
        sample = sorted_df.iloc[::step].head(top_k)

    return sample.to_dict(orient="records"), total_count


# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────
def handle_chat(user_message: str, knowledge_base,
                vector_store,
                session_id: str = "default") -> dict:

    if knowledge_base is None:
        return {"chatbot_reply": "HỆ THỐNG CHƯA SẴN SÀNG!"}

    # 1. Normalise & detect intent
    user_message_fixed = _normalize_user_message(user_message)
    msg_lower          = normalize_text(user_message_fixed)
    is_compat, has_cpu, has_gpu, has_main = _detect_intent(msg_lower)
    is_price_calc = is_price_calculation_query(msg_lower)
    category = _get_category(msg_lower)

    # 2. Lấy lịch sử TRƯỚC khi search (để reformulate)
    chat_history = get_trimmed_history(session_id)

    # 3. Reformulate query mơ hồ → rõ ràng trước khi search
    search_query = _reformulate_query(user_message_fixed, chat_history)
    q_clean = search_query.replace("\n", " ").strip()
    if len(q_clean) > 300:
        q_clean = q_clean[:100]

    # 3.5. Bóc tách ý định bằng LLM sớm để lấy chính xác loại linh kiện khách cần tìm
    intent = parse_compat_intent(search_query)
    if intent.looking_for != "none":
        category = intent.looking_for.upper()

    # 4. Fetch matched_items
    price_range = parse_price_range_vnd(user_message_fixed)
    brand = _detect_brand(msg_lower)
    total_count = None

    if price_range or (brand and category == "GPU"):
        lo, hi = price_range if price_range else (0.0, float("inf"))
        matched_items, total_count = _filter_knowledge_base_by_price(
            knowledge_base, category, lo, hi, brand=brand, top_k=10
        )
    else:
        matched_items = hybrid_search(q_clean, category, 4, knowledge_base, vector_store) or []

    if price_range and not matched_items:
        return {
            "chatbot_reply": (
                "Dạ hiện tại cửa hàng chưa có sản phẩm nào trong khoảng giá này ạ. "
                "Bạn có muốn em gợi ý mức giá gần nhất không?"
            )
        }

    # 5. Build compat context
    compatibility_context = ""
    if intent.intent == "compatibility":
        compatibility_context = build_compatibility_context(
            intent, knowledge_base, vector_store
        )
    elif intent.intent == "suggestion":
        compatibility_context = build_suggestion_context(
            intent, knowledge_base, vector_store
        )
    elif intent.intent == "price_calculation" or is_price_calc:
        compatibility_context = build_price_calculation_context(
            intent, knowledge_base, vector_store
        )
    # intent.intent == "none" (hoặc LLM lỗi) → context rỗng, rơi xuống
    # product_context bình thường, không crash.
    # 6. Build product context
    product_context = ""
    if not compatibility_context:
        product_context = _build_product_context(
            search_query, category, matched_items
        )

    # 7. Nothing found?
    if not compatibility_context and not product_context:
        return {
            "chatbot_reply": (
                "Dạ hiện tại em chưa tìm thấy mã sản phẩm này trong kho. "
                "Bạn cung cấp rõ tên model giúp em nhé!"
            )
        }

    # 8. Build context & format_hint
    context     = compatibility_context if compatibility_context else product_context
    format_hint = build_range_summary(user_message, matched_items) \
                  if not compatibility_context else ""

    if price_range and total_count and total_count > len(matched_items):
        format_hint += (
            f"\n(Lưu ý: còn {total_count - len(matched_items)} sản phẩm khác "
            f"cũng nằm trong khoảng giá này, không hiển thị hết ở đây.)"
        )

    # 9. Invoke chain với memory
    try:
        print("\n" + "═"*60)
        print(f"🔍 [HỆ THỐNG DEBUG CHAT] - Session ID: {session_id}")
        print(f"🔹 1. Câu hỏi gốc của khách: '{user_message}'")
        print(f"🔹 2. Từ khóa dùng để Search (q_clean): '{q_clean}'")
        print(f"🔹 3. Số lượng linh kiện tìm thấy trong DB: {len(matched_items)} món"
              + (f" (tổng khớp điều kiện giá: {total_count})" if total_count else ""))
        print(f"🔹 4. Nội dung [format_hint] sinh ra:\n{repr(format_hint)}")
        print(f"🔹 5. Nội dung [context] nhét vào miệng Bot:\n{context}")
        print("═"*60 + "\n")

        # Bẻ lái luồng chạy tại đây! Giao việc chuẩn cho từng Trạm
        if intent.intent == "compatibility":
            chain = _get_compat_check_chain()
        elif intent.intent == "suggestion":
            chain = _get_suggestion_chain()
        else:
            chain = _get_chain() # Rơi vào đây khi intent là "none" (hỏi giá, specs, tìm SP...)
       
        # Gọi AI xử lý với đúng Trạm đã chọn
        response = chain.invoke({
            "context":      context,
            "format_hint":  format_hint,
            "user_message": user_message_fixed,
            "chat_history": chat_history,
        })

        reply = response.content
        clean_reply = world_filter(reply)
        save_message(session_id, user_message_fixed, clean_reply)
        return {"chatbot_reply": clean_reply}

    except Exception as e:
        return {"chatbot_reply": f"❌ Lỗi bộ não AI: {str(e)}"}