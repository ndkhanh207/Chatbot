import re

MAX_HISTORY_MSGS = 4
MAX_HISTORY_CHAR_LIMIT = 200

def _extract_verified_state(chat_history: list) -> str:
    """Extract confirmed components and last intent from chat history.
    User messages are source of truth; AI suggestions fill missing slots."""
    CPU_RE  = re.compile(r'\b(i[3579][-\s]?\d{4,5}[a-z0-9]*|ryzen\s*[3579]\s+\d{4,5}[a-z0-9]*)\b', re.I)
    GPU_RE  = re.compile(r'\b(rtx\s*\d{3,4}(?:\s*ti)?|rx\s*\d{3,4}(?:\s*xt)?)\b', re.I)
    MAIN_RE = re.compile(r'\b([bzhx]\d{2,3}m?(?:-[a-z0-9]+)?)\b', re.I)
    CAT_RE  = re.compile(r'\b(gpu|cpu|mainboard|card đồ họa|bo mạch chủ|vga)\b', re.I)

    # Intent detection from user question patterns
    INTENT_PATTERNS = [
        (re.compile(r'lắp được|tương thích|đi với|chạy chung|hợp không|kết hợp|gắn được', re.I), "compatibility"),
        (re.compile(r'giá\s*bao nhiêu|giá\s*nhiêu|bao\s*nhiêu\s*tiền', re.I), "price_check"),
        (re.compile(r'vram|xung|socket|lõi|nhân|tdp|bộ nhớ|thông số|mượt|khỏe', re.I), "specification"),
        (re.compile(r'tìm|gợi ý|đề xuất|phù hợp', re.I), "suggestion"),
    ]

    user_state = {}   # confirmed by human turn
    ai_state   = {}   # suggested by AI (lower trust)
    last_intent = None

    for msg in reversed(chat_history[-6:]):
        role = getattr(msg, "type", "")
        c    = msg.content
        cpu  = CPU_RE.search(c)
        gpu  = GPU_RE.search(c)
        main = MAIN_RE.search(c)
        cat  = CAT_RE.search(c)
        if role == "human":
            if cpu:  user_state.setdefault("cpu", cpu.group(1))
            if gpu:  user_state.setdefault("gpu", gpu.group(1))
            if main: user_state.setdefault("mainboard", main.group(1))
            if cat:  user_state.setdefault("category", cat.group(1).lower())
            # Extract intent from user's most recent explicit question
            if last_intent is None:
                for pattern, intent_name in INTENT_PATTERNS:
                    if pattern.search(c):
                        last_intent = intent_name
                        break
        elif role == "ai":
            if cpu:  ai_state.setdefault("cpu", cpu.group(1))
            if gpu:  ai_state.setdefault("gpu", gpu.group(1))
            if main: ai_state.setdefault("mainboard", main.group(1))
            if cat:  ai_state.setdefault("category", cat.group(1).lower())

    # Merge: user confirmation wins; AI suggestion only fills missing slots
    state = {**ai_state, **user_state}
    
    if last_intent is None:
        for msg in reversed(chat_history[-6:]):
            if getattr(msg, "type", "") == "ai":
                c = msg.content
                if re.search(r'vnđ|giá là|giá của|giá:\s*\d', c, re.I):
                    last_intent = "price_check"
                    break
                if re.search(r'\bmhz\b|\bghz\b|xung|bộ nhớ|socket|lõi', c, re.I):
                    last_intent = "specification"
                    break
                if re.search(r'tương thích|không tương thích|lắp được|phù hợp', c, re.I):
                    last_intent = "compatibility"
                    break

    if last_intent:
        state["last_intent"] = last_intent
    return ", ".join(f"{k.upper()}={v}" for k, v in state.items())

def build_history_context(chat_history: list = None) -> str:
    if not chat_history:
        return ""
    
    # Extract verified state from AI messages
    verified_state = _extract_verified_state(chat_history)
    
    context = ""
    if verified_state:
        context += f"[TRẠNG THÁI ĐÃ XÁC NHẬN]:\n{verified_state}\n\n"
    
    context += "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\n"
    for msg in chat_history[-MAX_HISTORY_MSGS:]:
        role = "Khách" if getattr(msg, "type", "") == "human" else "AI"
        content = msg.content
        if role == "AI" and len(content) > MAX_HISTORY_CHAR_LIMIT:
            content = content[:MAX_HISTORY_CHAR_LIMIT] + "..."
        context += f"{role}: {content}\n"
    return context + "\n"
