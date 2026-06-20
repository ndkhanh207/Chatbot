import re
import pandas as pd


def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Lowercase + chuẩn hóa khoảng trắng (giữ space để keyword matching hoạt động)
    return re.sub(r'\s+', ' ', text.lower()).strip()