import re
from typing import Optional

def detect_brand(msg_lower: str) -> Optional[str]:
    """Trả về từ khóa khớp với cột 'chipset' của GPU trong dataset thực tế."""
    if "nvidia" in msg_lower or "rtx" in msg_lower or "gtx" in msg_lower:
        return "geforce"
    if "amd" in msg_lower or "radeon" in msg_lower or " rx " in msg_lower:
        return "radeon"
    return None
