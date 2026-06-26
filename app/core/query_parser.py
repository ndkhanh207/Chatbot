from typing import Optional
from app.constants import *
from app.compatibility.compat_logic import is_compatibility_query
import re

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
    msg = msg.replace(r'\bchip\b',          "cpu")
    msg = msg.replace("card đồ họa",   "gpu")
    msg = msg.replace("vga",           "gpu")
    msg = msg.replace("đồ họa",        "gpu")
    msg = re.sub(r'\bcard\b', 'gpu', msg)
    # tdp
    msg = msg.replace("điện năng tiêu thụ", "tdp")
    msg = msg.replace("điện năng",     "tdp")
    return msg

def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Lowercase + chuẩn hóa khoảng trắng (giữ space để keyword matching hoạt động)
    return re.sub(r'\s+', ' ', text.lower()).strip()
    
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