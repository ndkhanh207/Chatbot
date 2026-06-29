"""
Module chuyên dụng kiểm tra và ngăn chặn Prompt Injection / Jailbreak.
"""
import re

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

def sanitize_input(text: str) -> tuple[str, bool]:
    """
    Kiểm tra prompt injection. Trả về (text_gốc, is_injection).
    Nếu phát hiện injection pattern → is_injection = True.
    """
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            print(f"[SECURITY] Phát hiện injection attempt: '{text[:100]}...'")
            return text, True
    return text, False
