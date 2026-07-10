import re
from typing import Optional
from app.constants import *
from app.compatibility.compat_logic import is_compatibility_query

_MODEL_PATTERN = re.compile(
    r'(rtx|gtx|rx)\s*-?\s*(\d{3,4})\s*(ti|xt|gre|super|xtx)?',
    re.IGNORECASE,
)

def normalize_user_message(user_message: str) -> str:
    msg = user_message.lower()
    # Thay thế compound trước, rồi mới thay từ đơn
    # (tránh "mainboard" bị tách thành "bo mạch chủboard")
    # main 
    msg = re.sub(r'\bmainboard\b', 'bo mạch chủ', msg)
    msg = re.sub(r'\bmain\b',      'bo mạch chủ', msg)
    # card 
    msg = re.sub(r'\bchip\b', 'cpu', msg)
    msg = msg.replace("card đồ họa",   "gpu")
    msg = msg.replace("vga",           "gpu")
    msg = msg.replace("đồ họa",        "gpu")
    msg = re.sub(r'\bcard\b', 'gpu', msg)
    # tdp
    msg = msg.replace("điện năng tiêu thụ", "tdp")
    msg = msg.replace("điện năng",     "tdp")
    return msg

_STOPWORDS = {"thế", "còn", "thì", "sao", "giá", "bao", "nhiêu", "tư", "vấn", "tìm", "cho", "mình", "loại", "nào", "tốt", "bạn", "ạ", "dạ", "chào"}

def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Xóa dấu chấm hỏi, phẩy, chấm, chấm than để không dính vào token
    text = re.sub(r'[?!.,;]', ' ', text.lower())
    # Chuẩn hóa khoảng trắng
    return re.sub(r'\s+', ' ', text).strip()

def clean_search_query(text: str) -> str:
    """Loại bỏ stopwords để hỗ trợ hybrid_search keyword_scores"""
    text = normalize_text(text)
    words = text.split()
    filtered_words = [w for w in words if w not in _STOPWORDS]
    return " ".join(filtered_words)
    
OWNERSHIP_HINTS = ['tôi có', 'tôi đã có', 'sẵn có', 'đang dùng', 'đang có']

def has_ownership_signal(msg_lower: str) -> bool:
    return any(h in msg_lower for h in OWNERSHIP_HINTS)

def detect_intent(msg_lower: str):
    is_compat = is_compatibility_query(msg_lower)
    has_cpu   = any(w in msg_lower for w in CPU_TERMS)
    has_gpu   = any(w in msg_lower for w in GPU_TERMS)
    has_main  = any(w in msg_lower for w in MAIN_TERMS)
    return is_compat, has_cpu, has_gpu, has_main

def get_category(msg_lower: str) -> str | None:
    first_idx = float('inf')
    best_cat = None
    
    for cat_name, terms in [('MAINBOARD', MAIN_TERMS), ('GPU', GPU_TERMS), ('CPU', CPU_TERMS)]:
        for term in terms:
            idx = msg_lower.find(term)
            if idx != -1 and idx < first_idx:
                first_idx = idx
                best_cat = cat_name
                
    return best_cat

def detect_brand(msg_lower: str) -> Optional[str]:
    """Trả về từ khóa khớp với cột 'chipset' của GPU trong dataset thực tế."""
    if "nvidia" in msg_lower or "rtx" in msg_lower or "gtx" in msg_lower:
        return "geforce"
    if "amd" in msg_lower or "radeon" in msg_lower or " rx " in msg_lower:
        return "radeon"
    return None




def detect_model_query(msg_lower: str) -> Optional[dict]:
    """
    Phát hiện dòng GPU cụ thể trong câu hỏi, vd 'rtx 4070' → {'digits': '4070', 'suffix': None}.
    Trả None nếu không có model cụ thể nào (để chat_handler fallback qua brand-wide hoặc
    semantic search bình thường).
    """
    m = _MODEL_PATTERN.search(msg_lower)
    if not m:
        return None
    return {"digits": m.group(2), "suffix": m.group(3) or None}

FOLLOW_UP_MARKERS = ("vậy", "thì sao", "thế còn", "còn", "nó", "con này", "của")
EXPLICIT_FOCUS_MARKERS = (
    "giá", "bao nhiêu", "xung", "vram", "socket", "tdp", "bộ nhớ",
    "triệu", "tr", "tầm", "khoảng", "dưới", "trên", "mượt",
)

def build_recent_user_focus(user_message: str, chat_history: list, max_chars: int = 180) -> str:
    msg_lower = user_message.lower()
    if not any(marker in msg_lower for marker in FOLLOW_UP_MARKERS):
        return ""

    previous_user_msg = next(
        (m.content.strip() for m in reversed(chat_history) if getattr(m, "type", "") == "human" and m.content.strip()),
        ""
    )
    if not previous_user_msg:
        return ""

    previous_user_msg = previous_user_msg.replace("\n", " ")
    if len(previous_user_msg) > max_chars:
        previous_user_msg = previous_user_msg[:max_chars].rstrip() + "..."

    if any(marker in msg_lower for marker in EXPLICIT_FOCUS_MARKERS):
        return (
            f"Câu hỏi hiện tại có nhu cầu mới rõ ràng; chỉ kế thừa linh kiện/danh mục còn thiếu từ câu trước: "
            f"'{previous_user_msg}'. Ưu tiên đúng nội dung câu hiện tại."
        )

    return (
        f"Câu hỏi hiện tại đang nối tiếp cùng nhu cầu/chủ đề của câu trước: '{previous_user_msg}'. "
        "Hãy trả lời đúng nhu cầu đó cho câu hiện tại; không tự chuyển sang giá hoặc xung nếu khách không hỏi."
    )