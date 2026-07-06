# app/pc_builder/history_utils.py
import re
from .constants import (
    AI_BUDGET_KEYWORDS, AI_BUDGET_REGEX_PATTERNS,
    AI_PURPOSE_KEYWORDS, AI_BUILD_CONTEXT_KEYWORDS
)
from .extractor import extract_budget, extract_quantity, extract_component_filter, extract_brand_filter, is_reset_intent
from app.core.intent.history_context import CPU_RE, GPU_RE, MAIN_RE

# ──────────────────────────────────────────────
# Compiled regex (biên dịch 1 lần, dùng nhiều lần — hiệu năng tốt hơn)
# ──────────────────────────────────────────────
_BUDGET_REGEX_COMPILED = [re.compile(p, re.IGNORECASE) for p in AI_BUDGET_REGEX_PATTERNS]


def ai_asked_for_budget(chat_history: list) -> bool:
    """
    Kiểm tra xem AI vừa hỏi ngân sách ở tin nhắn trước không.
    Dùng kết hợp: keyword cứng (nhanh) + regex (linh hoạt).
    """
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai':
            content = msg.content.lower()
            # Kiểm tra keyword cứng trước (nhanh)
            if any(kw in content for kw in AI_BUDGET_KEYWORDS):
                return True
            # Kiểm tra regex (bắt thêm biến thể tự nhiên)
            if any(rx.search(content) for rx in _BUDGET_REGEX_COMPILED):
                return True
            return False  # Tin AI gần nhất không hỏi budget
    return False


def ai_asked_for_purpose(chat_history: list) -> bool:
    """Kiểm tra xem AI vừa hỏi nhu cầu/mục đích ở tin nhắn trước không."""
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai':
            content = msg.content.lower()
            if any(kw in content for kw in AI_PURPOSE_KEYWORDS):
                return True
            return False
    return False


def is_build_context_active(chat_history: list) -> bool:
    """Kiểm tra xem lịch sử gần nhất có đang trong luồng tư vấn PC không."""
    ai_msg_count = 0
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai':
            ai_msg_count += 1
            content = msg.content.lower()
            if '[gợi ý bộ pc tối ưu]' in content:
                return True
            if any(kw in content for kw in AI_BUILD_CONTEXT_KEYWORDS):
                return True
            if ai_msg_count >= 2:
                break
    return False


def inherit_budget(msg_lower: str, ctx_budget: int | None) -> int | None:
    """
    Điều chỉnh ngân sách hiện tại nếu người dùng có từ khóa tăng/giảm.
    """
    if ctx_budget is None:
        return None

    # Nếu user đồng ý tăng ngân sách theo đề xuất của AI (out of budget prompt)
    if re.search(r'\b(ok|oke|đồng ý|có|tăng đi|được|okela|triển)\b', msg_lower):
        # Không có giá trị cụ thể, tăng nhẹ 15% hoặc giữ nguyên để LLM xử lý
        return int(ctx_budget * 1.15)

    if re.search(r'\b(cao hơn|đắt hơn|mạnh hơn|ngon hơn)\b', msg_lower):
        return int(ctx_budget * 1.3)
    elif re.search(r'\b(thấp hơn|rẻ hơn|yếu hơn|bèo hơn)\b', msg_lower):
        return int(ctx_budget * 0.7)
        
    return ctx_budget


def inherit_quantity(chat_history: list) -> int:
    """Kế thừa số lượng bộ PC từ lịch sử chat."""
    if not chat_history:
        return 1
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'human':
            if is_reset_intent(msg.content):
                break
            hist_qty = extract_quantity(msg.content)
            if hist_qty > 1:
                return hist_qty
    return 1


def inherit_component_intent(chat_history: list, max_turns: int = 4) -> dict:
    """
    Quét N lượt chat gần nhất để kế thừa linh kiện user đã nhắc tới.
    Không yêu cầu context phải là "tư vấn PC" trước đó.
    """
    result = {'cpu_model': None, 'gpu_model': None, 'cpu_brand': None, 'gpu_brand': None}
    turns_scanned = 0

    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'human':
            if is_reset_intent(msg.content):
                break
            if turns_scanned >= max_turns:
                break
            turns_scanned += 1
            comp = extract_component_filter(msg.content)
            brand = extract_brand_filter(msg.content)

            # Lấy lần đầu tìm thấy mỗi loại (gần nhất = ưu tiên nhất)
            if not result['cpu_model'] and comp.get('cpu_model'):
                result['cpu_model'] = comp['cpu_model']
            if not result['gpu_model'] and comp.get('gpu_model'):
                result['gpu_model'] = comp['gpu_model']
            if not result['cpu_brand'] and brand.get('cpu_brand'):
                result['cpu_brand'] = brand['cpu_brand']
            if not result['gpu_brand'] and brand.get('gpu_brand'):
                result['gpu_brand'] = brand['gpu_brand']

    return result
