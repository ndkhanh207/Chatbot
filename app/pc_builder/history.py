# app/pc_builder/history_utils.py
import re
from .constants import AI_BUDGET_KEYWORDS, AI_PURPOSE_KEYWORDS, AI_BUILD_CONTEXT_KEYWORDS
from .extractor import extract_budget, extract_quantity, extract_component_filter, extract_brand_filter, is_reset_intent

def ai_asked_for_budget(chat_history: list) -> bool:
    """Kiểm tra xem AI vừa hỏi ngân sách ở tin nhắn trước không."""
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai':
            content = msg.content.lower()
            if any(kw in content for kw in AI_BUDGET_KEYWORDS):
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

def get_exclude_builds(chat_history: list) -> list:
    """Lấy danh sách BuildID đã gợi ý để tránh lặp."""
    exclude = []
    if chat_history:
        for msg in reversed(chat_history):
            if getattr(msg, 'type', '') == 'ai':
                m = re.search(r'Mã bộ\s*:\s*(BUILD-\d+)', msg.content)
                if m:
                    exclude.append(m.group(1).strip())
    return exclude

def get_last_build_id(chat_history: list) -> str | None:
    """Lấy BuildID gần nhất từ lịch sử."""
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai':
            m = re.search(r'Mã bộ\s*:\s*(BUILD-\d+)', msg.content)
            if m:
                return m.group(1).strip()
    return None

def inherit_budget(msg_lower: str, chat_history: list) -> int | None:
    """Kế thừa ngân sách từ lịch sử, điều chỉnh nếu có từ khóa cao/thấp hơn."""
    if not chat_history:
        return None
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'human':
            hist_budget = extract_budget(msg.content)
            if hist_budget is not None:
                if re.search(r'\b(cao hơn|đắt hơn|mạnh hơn|ngon hơn)\b', msg_lower):
                    return int(hist_budget * 1.3)
                elif re.search(r'\b(thấp hơn|rẻ hơn|yếu hơn|bèo hơn)\b', msg_lower):
                    return int(hist_budget * 0.7)
                return hist_budget
    return None

def inherit_quantity(chat_history: list) -> int:
    """Kế thừa số lượng bộ PC từ lịch sử chat."""
    if not chat_history:
        return 1
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'human':
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
