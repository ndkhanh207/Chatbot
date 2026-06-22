# chat_handler.py
"""
Chat endpoint logic — dùng LangChain ChatOllama + ChatPromptTemplate.
"""

import re
import ollama

from langchain_ollama import ChatOllama
from langchain_core.runnables import RunnableSequence

from app.utils.model_utils import get_ollama_model
from app.pc_builder.compatibility import build_compatibility_context
from app.utils.common import format_currency_vietnam, normalize_text
from app.utils.tools import CONVERSIONS, convert_if_needed, ALIASES
from app.utils.units import get_unit_map
from app.templates.prompt_templates import ADVISOR_TEMPLATE, REFORMULATE_TEMPLATE, PC_BUILD_TEMPLATE
from app.utils.response_formatter import build_format_hint
from app.memory.memory_store import get_trimmed_history, save_message
from app.pc_builder.advisor import (
    detect_build_pc_intent,
    extract_budget,
    find_best_build,
    format_build_context,
)
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
# Prompt Injection Guard
# ──────────────────────────────────────────────
INJECTION_PATTERNS = [
    # English jailbreak patterns
    r'(ignore|forget|disregard|override).{0,30}(instruction|prompt|system|above|rule)',
    r'(you are now|act as|pretend to be|roleplay as|simulate)',
    r'(repeat after me|say exactly|output the following)',
    r'(DAN|jailbreak|developer mode|unrestricted)',
    r'(##system|<\|im_start\|>|<\|system\|>|\[system\]|\[INST\])',  # Special tokens
    # Vietnamese jailbreak patterns
    r'(bỏ qua|quên|ghi đè|vô hiệu hóa).{0,40}(hướng dẫn|lệnh|quy tắc|system|trên)',
    r'(từ giờ|bây giờ|hãy).{0,20}(bạn là|bạn không còn|đóng vai|giả vờ)',
    r'(lặp lại|nhắc lại).{0,10}(sau tôi|chính xác)',
    r'(không có giới hạn|không bị kiểm duyệt|chế độ nhà phát triển)',
]

MAX_INPUT_LENGTH = 500  # Ký tự tối đa

def _sanitize_input(text: str) -> tuple[str, bool]:
    """
    Kiểm tra prompt injection. Trả về (text_gốc, is_injection).
    Nếu phát hiện injection pattern → is_injection = True.
    """
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            print(f"[SECURITY] Phát hiện injection attempt: '{text[:100]}...'")
            return text, True
    return text, False

_reformulate_chain = None

# ──────────────────────────────────────────────
# LangChain chain — khởi tạo lazy (tránh lỗi khi
# Ollama chưa chạy lúc import)
# ──────────────────────────────────────────────
_chain: RunnableSequence | None = None
_pc_build_chain: RunnableSequence | None = None

def _get_chain() -> RunnableSequence:
    """Trả về chain, tạo mới nếu chưa có."""
    global _chain
    if _chain is None:
        llm = ChatOllama(
            model=get_ollama_model(),
            temperature=0.1,      # Tránh 0.0 tuyệt đối để không bị loop
            top_p=0.1,
            repeat_penalty=1.2,   # Hình phạt nặng nếu lặp lại từ
        )
        _chain = ADVISOR_TEMPLATE | llm
    return _chain

def _get_pc_build_chain() -> RunnableSequence:
    """Trả về chain dành riêng cho tư vấn bộ PC, tạo mới nếu chưa có."""
    global _pc_build_chain
    if _pc_build_chain is None:
        llm = ChatOllama(
            model=get_ollama_model(),
            temperature=0.1,      # Hạ nhiệt độ để chống bịa đặt nhưng tránh 0.0
            top_p=0.1,
            repeat_penalty=1.2,
        )
        _pc_build_chain = PC_BUILD_TEMPLATE | llm
    return _pc_build_chain

def _get_reformulate_chain():
    global _reformulate_chain
    if _reformulate_chain is None:
        _reformulate_chain = REFORMULATE_TEMPLATE | ChatOllama(
            model=get_ollama_model(),
            temperature=0.0,
            repeat_penalty=1.2,
        )
    return _reformulate_chain


def _reformulate_query(user_message: str, chat_history: list) -> str:
    if not chat_history:
        return user_message

    # BUG 7: Nếu câu hỏi chỉ chứa số tiền (trả lời ngân sách) → không cần Reformulate
    # Ví dụ: "giá 30 triệu đi", "30 triệu", "tầm 20tr"
    budget_only = re.match(
        r'^[\s\w]*(\d+(?:[.,]\d+)?\s*(?:triệu|tr|m|000[,.]?000))[\s\w!.,?]*$',
        user_message.strip(), re.IGNORECASE
    )
    if budget_only:
        return user_message

    specific_terms = ['rtx', 'gtx', 'rx', 'i3', 'i5', 'i7', 'i9',
                      'ryzen', 'b760', 'z790', 'x670', 'h610']
    if any(t in user_message.lower() for t in specific_terms):
        return user_message
    # Trích xuất đúng câu trả lời cuối cùng của AI, ưu tiên tìm bảng Gợi ý bộ PC
    last_ai_msg = ""
    last_build_msg = ""
    for msg in reversed(chat_history):
        if getattr(msg, "type", "") == "ai":
            if not last_ai_msg:
                last_ai_msg = msg.content
            if "[GỢI Ý BỘ PC TỐI ƯU]" in msg.content:
                last_build_msg = msg.content
                break
                
    context_msg = last_build_msg if last_build_msg else last_ai_msg

    # ── FAST PATH: Phân giải đại từ bằng code thuần (chống ảo giác AI 100%) ──
    if last_ai_msg:
        user_msg_lower = user_message.lower()
        
        cpu_match  = re.search(r'-\s*CPU\s*:\s*(.+?)\s*\|', context_msg, re.IGNORECASE)
        gpu_match  = re.search(r'-\s*GPU\s*:\s*(.+?)\s*\|', context_msg, re.IGNORECASE)
        main_match = re.search(r'-\s*Mainboard\s*:\s*(.+?)\s*\|', context_msg, re.IGNORECASE)
        
        replaced_msg = user_msg_lower
        matched = False
        
        if cpu_match and re.search(r'\b(cpu)\b', user_msg_lower):
            cpu_name = cpu_match.group(1).strip()
            replaced_msg = re.sub(r'\b(con cpu|cpu)\b', cpu_name, replaced_msg)
            matched = True
            
        if gpu_match and re.search(r'\b(gpu)\b', user_msg_lower):
            gpu_name = gpu_match.group(1).strip()
            replaced_msg = re.sub(r'\b(con gpu|gpu)\b', gpu_name, replaced_msg)
            matched = True
            
        if main_match and re.search(r'\b(bo mạch chủ)\b', user_msg_lower):
            main_name = main_match.group(1).strip()
            replaced_msg = re.sub(r'\b(con bo mạch chủ|bo mạch chủ)\b', main_name, replaced_msg)
            matched = True
            
        if matched:
            print(f"[REFORMULATE - REGEX] '{user_message}' → '{replaced_msg}'")
            return replaced_msg

    # ── FALLBACK: Nếu code thuần không bắt được thì gọi AI ──
    try:
        # Sanitize last_ai_msg để tránh stored injection từ lịch sử
        safe_context_msg = context_msg[:800] if context_msg else ""  # Giới hạn 800 ký tự
        response = _get_reformulate_chain().invoke({
            "user_message": user_message,
            "last_ai_msg": safe_context_msg,
        })
        reformulated = response.content.strip()
        
        # Fail-safe: nếu AI trả về rỗng hoặc quá dài (ảo giác), dùng câu gốc
        if not reformulated or len(reformulated) > len(user_message) * 4:
            reformulated = user_message

        print(f"[REFORMULATE - AI] '{user_message}' → '{reformulated}'")
        return reformulated
    except Exception as e:
        print(f"[REFORMULATE - LỖI] {e}")
        return user_message

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
                compatibility_rules, search_fn,
                session_id: str = "default",
                build_df=None) -> dict:

    if knowledge_base is None:
        return {"chatbot_reply": "HỆ THỐNG CHƯA SẴN SÀNG!"}

    # ── Security: Kiểm tra độ dài và Prompt Injection ──
    if len(user_message) > MAX_INPUT_LENGTH:
        return {"chatbot_reply": "Câu hỏi quá dài rồi ạ! Bạn vui lòng rút gọn trong 500 ký tự giúp em nhé 😊"}

    _, is_injection = _sanitize_input(user_message)
    if is_injection:
        return {"chatbot_reply": "Dạ em chỉ hỗ trợ tư vấn linh kiện và bộ máy tính thôi ạ! Bạn có câu hỏi nào về PC không? 😊"}

    msg_clean = user_message.strip().lower()

    # ── FEATURE: Giao tiếp cơ bản (Không gọi DB / LLM) ──
    CASUAL_GREETINGS = ['xin chào', 'chào bạn', 'hi', 'hello', 'chào em', 'chào bot']
    CASUAL_THANKS = ['cảm ơn', 'thank', 'tks', 'ok', 'oke', 'okela', 'dạ', 'vâng', 'tuyệt vời', 'đã hiểu', 'hay quá']
    CASUAL_BYE = ['tạm biệt', 'bye', 'hẹn gặp lại']

    if len(msg_clean) < 30:
        if any(msg_clean == g or msg_clean.startswith(g + ' ') for g in CASUAL_GREETINGS):
            return {"chatbot_reply": "Dạ em chào bạn! Em là trợ lý tư vấn máy tính, em có thể giúp gì cho bạn hôm nay ạ? 😊"}
        if any(msg_clean == t or msg_clean.startswith(t + ' ') for t in CASUAL_THANKS):
            return {"chatbot_reply": "Dạ vâng ạ! Nếu bạn cần tư vấn cấu hình hay linh kiện gì thêm cứ nhắn em nhé. 😊"}
        if any(msg_clean == b or msg_clean.startswith(b + ' ') for b in CASUAL_BYE):
            return {"chatbot_reply": "Dạ tạm biệt bạn! Chúc bạn một ngày tốt lành ạ! 😊"}

    # ── FEATURE: Off-topic guard rail ──
    # Chặn các câu hỏi hoàn toàn ngoài lĩnh vực PC
    OFF_TOPIC_TRIGGERS = [
        'laptop', 'macbook', 'điện thoại', 'smartphone', 'iphone', 'samsung',
        'tivi', 'máy lạnh', 'điều hòa', 'tủ lạnh', 'máy giặt',
        'xe máy', 'ô tô', 'xe hơi', 'xe đạp',
        'thời tiết', 'nấu ăn', 'công thức', 'quần áo', 'thời trang', 'giày',
        'chứng khoán', 'bitcoin', 'crypto', 'cổ phiếu',
        'bóng đá', 'thể thao', 'ca sĩ', 'diễn viên', 'phim', 'nhạc',
        'làm thơ', 'kể chuyện', 'viết code', 'viết bài', 'giải toán'
    ]
    msg_lower_check = user_message.lower()
    # Chỉ từ chối nếu off-topic VÀ không liên quan gì đến PC/linh kiện
    PC_SAFE_TERMS = ['pc', 'cpu', 'gpu', 'ram', 'ssd', 'vga', 'card', 'mainboard', 'build', 'máy tính']
    is_off_topic = any(t in msg_lower_check for t in OFF_TOPIC_TRIGGERS)
    is_pc_related = any(t in msg_lower_check for t in PC_SAFE_TERMS)
    if is_off_topic and not is_pc_related:
        return {"chatbot_reply": "Dạ em chỉ chuyên tư vấn linh kiện và cấu hình máy tính để bàn thôi ạ! Bạn có cần tư vấn CPU, GPU, hay build bộ PC không? 😊"}

    # ── 0. PC Build intent — xử lý trước tất cả các intent khác ──
    user_message_fixed = _normalize_user_message(user_message)
    msg_lower = normalize_text(user_message_fixed)
    is_build_pc = detect_build_pc_intent(user_message_fixed)
    chat_history = get_trimmed_history(session_id)

    # Chuyển quyền xử lý luồng PC Build sang module riêng biệt
    from app.pc_builder.flow import handle_pc_build_flow
    pc_build_result = handle_pc_build_flow(
        session_id=session_id,
        user_message=user_message,
        user_message_fixed=user_message_fixed,
        msg_lower=msg_lower,
        chat_history=chat_history,
        build_df=build_df,
        is_build_pc=is_build_pc
    )
    if pc_build_result is not None:
        return pc_build_result

    # 1. Normalise & detect intent
    user_message_fixed = _normalize_user_message(user_message)
    msg_lower          = normalize_text(user_message_fixed)
    is_compat, has_cpu, has_gpu, has_main = _detect_intent(msg_lower)
    category = _get_category(has_gpu, has_cpu, has_main)

       # 2. Lấy lịch sử TRƯỚC khi search (để reformulate)
    chat_history = get_trimmed_history(session_id)

    # 3. Reformulate query mơ hồ → rõ ràng trước khi search
    search_query = _reformulate_query(user_message_fixed, chat_history)

    # 4. Fetch matched_items bằng query đã reformulate
    matched_items = search_fn(
        q=search_query,        # ← dùng query đã reformulate
        category=category,
        top_k=4
    ) or []

    # 5. Build compat context
    compatibility_context = ""
    if is_compat:
        compatibility_context = build_compatibility_context(
            search_query, knowledge_base, compatibility_rules, search_fn
        )

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
    format_hint = build_format_hint(user_message, matched_items) \
                  if not compatibility_context else ""

    # ====== DEBUG REGULAR CHAT ======
    print("\n" + "═" * 60)
    print(f"🔍 [HỆ THỐNG DEBUG CHAT] - Session ID: {session_id}")
    print(f"🔹 1. Câu hỏi gốc của khách: '{user_message_fixed}'")
    print(f"🔹 2. Từ khóa dùng để Search (q_clean): '{search_query}'")
    print(f"🔹 3. Số lượng linh kiện tìm thấy trong DB: {len(matched_items)} món")
    print(f"🔹 4. Nội dung [format_hint] sinh ra:\n{repr(format_hint)}")
    print(f"🔹 5. Nội dung [context] nhét vào miệng Bot:\n{context}")
    print("═" * 60 + "\n")

    # 9. Invoke chain với memory
    try:
        chain    = _get_chain()
        response = chain.invoke({
            "context":      context,
            "format_hint":  format_hint,
            "user_message": user_message_fixed,  # ← vẫn dùng câu gốc cho LLM
            "chat_history": chat_history,
        })

        reply = response.content
        save_message(session_id, user_message_fixed, reply)
        return {"chatbot_reply": reply}

    except Exception as e:
        return {"chatbot_reply": f"❌ Lỗi bộ não AI: {str(e)}"}