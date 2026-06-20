from typing import Optional
from app.compact.compatibility import is_compatibility_query, CPU_TERMS, GPU_TERMS, MAIN_TERMS
import re

def normalize_user_message(user_message: str) -> str:
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

def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Lowercase + chuẩn hóa khoảng trắng (giữ space để keyword matching hoạt động)
    return re.sub(r'\s+', ' ', text.lower()).strip()