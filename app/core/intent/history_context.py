import re

MAX_HISTORY_MSGS = 4
MAX_HISTORY_CHAR_LIMIT = 200

# Centralized Regex for component extraction across the system
CPU_RE  = re.compile(r'\b(i[3579](?:-?\d{4,5}[a-z0-9]*)?|ryzen\s*[3579](?:\s*\d{3,5}[a-z0-9]*)?|core\s*ultra\s*\d+|x3d)\b', re.I)
GPU_RE  = re.compile(r'\b(rtx|gtx|rx|arc)\s*(\d{3,5}(?:\s*ti|\s*xt|\s*xtx|\s*gre)?)\b', re.I)
MAIN_RE = re.compile(r'\b([bzhx]\d{2,3}m?(?:-[a-z0-9]+)?)\b', re.I)
CAT_RE  = re.compile(r'\b(gpu|cpu|mainboard|card đồ họa|bo mạch chủ|vga)\b', re.I)

def _extract_verified_state(chat_history: list) -> str:
    """Extract confirmed components and last intent from chat history.
    User messages are source of truth; AI suggestions fill missing slots."""
    INTENT_PATTERNS = [
        (re.compile(r'lắp được|tương thích|đi với|chạy chung|hợp không|kết hợp|gắn được', re.I), "compatibility"),
        (re.compile(r'giá\s*bao nhiêu|giá\s*nhiêu|bao\s*nhiêu\s*tiền', re.I), "price_check"),
        (re.compile(r'vram|xung|socket|lõi|nhân|tdp|bộ nhớ|thông số|mượt|khỏe', re.I), "specification"),
        (re.compile(r'tìm|gợi ý|đề xuất|phù hợp', re.I), "suggestion"),
        (re.compile(r'build|ráp|tư vấn pc|cấu hình', re.I), "build_pc"),
    ]

    state = {}
    last_intent = None

    for msg in reversed(chat_history[-6:]):
        role = getattr(msg, "type", "")
        c    = msg.content
        cpu_m = CPU_RE.search(c)
        gpu_m = GPU_RE.search(c)
        main_m = MAIN_RE.search(c)
        cat_m = CAT_RE.search(c)
        
        cpu = cpu_m.group(0).strip() if cpu_m else None
        gpu = gpu_m.group(0).strip() if gpu_m else None
        main = main_m.group(1).strip() if main_m else None
        cat = cat_m.group(1).lower().strip() if cat_m else None
        
        if role == "human":
            if cpu:  state.setdefault("cpu", cpu)
            if gpu:  state.setdefault("gpu", gpu)
            if main: state.setdefault("mainboard", main)
            if cat:  state.setdefault("category", cat)
            # Extract intent from user's most recent explicit question
            if last_intent is None:
                for pattern, intent_name in INTENT_PATTERNS:
                    if pattern.search(c):
                        last_intent = intent_name
                        break
        elif role == "ai":
            kwargs = getattr(msg, "additional_kwargs", {})
            if kwargs:
                meta_cpu = kwargs.get("user_cpu") or kwargs.get("last_suggested_cpu")
                meta_gpu = kwargs.get("user_gpu") or kwargs.get("last_suggested_gpu")
                meta_main = kwargs.get("user_mainboard") or kwargs.get("last_suggested_mainboard")
                
                if meta_cpu: state.setdefault("cpu", meta_cpu)
                if meta_gpu: state.setdefault("gpu", meta_gpu)
                if meta_main: state.setdefault("mainboard", meta_main)

            if cpu:  state.setdefault("cpu", cpu)
            if gpu:  state.setdefault("gpu", gpu)
            if main: state.setdefault("mainboard", main)
            if cat:  state.setdefault("category", cat)
    
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
                if re.search(r'bộ pc|cấu hình|mã bộ:\s*build-|để build bộ máy', c, re.I):
                    last_intent = "build_pc"
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
