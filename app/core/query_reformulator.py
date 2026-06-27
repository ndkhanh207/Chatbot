import re

from app.core.llm_chains import get_reformulate_chain

# ⭐ Phát hiện hallucination bằng PATTERN (số + đơn vị kỹ thuật), không liệt
# kê từng cụm từ cố định — markers cố định luôn bị lách khi model diễn đạt
# khác đi (vd "12GB GDDR6X" không khớp marker "vnđ"/"dạ,"/...).
_SPEC_VALUE_PATTERN = re.compile(
    r'\d+(\.\d+)?\s*(gb|gib|mb|tb|mhz|ghz|w|vnđ|đồng)\b', re.IGNORECASE
)
_ANSWER_PHRASE_MARKERS = ['tôi sẽ đề xuất', 'dạ,', 'bạn nên chọn', 'câu trả lời',
                          'tôi hiểu', 'bạn có thể', 'tôi không']

# Trích chủ ngữ đứng trước "có"/"là" — dùng khi model đã hallucinate trả lời
# nhưng vẫn xác định ĐÚNG sản phẩm từ history; tái dùng chủ ngữ này để thế
# vào đại từ trong câu hỏi gốc, tránh mất khả năng resolve "nó/này/đó".
_SUBJECT_PATTERN = re.compile(r'^(.*?)\s+(có|là)\s+', re.IGNORECASE)

# Tiền tố AI thường gắn vào đầu câu — cần loại trước khi trích chủ ngữ
_AI_PREFIX_PATTERN = re.compile(r'^(dạ[,.]?\s*|vâng[,.]?\s*)', re.IGNORECASE)

# Đại từ mơ hồ cần resolve (có thể mở rộng thêm)
_PRONOUN_PATTERN = re.compile(r'\b(nó|này|đó|con này|cái này|con đó|cái đó)\b', re.IGNORECASE)

MAX_SUBJECT_LEN = 60  # Subject dài hơn ngưỡng này → garbage, bỏ qua


def looks_like_full_answer(original: str, reformulated: str) -> bool:
    """
    Phát hiện khi reformulate chain trả lời luôn thay vì chỉ viết lại câu hỏi.
    Tổng quát hơn marker cố định: nếu output xuất hiện số+đơn vị kỹ thuật
    (GB/MHz/W/VNĐ...) mà câu hỏi GỐC không hề có số nào — gần như chắc chắn
    model đã tự trả lời thay vì viết lại câu hỏi.
    """
    if _SPEC_VALUE_PATTERN.search(reformulated) and not _SPEC_VALUE_PATTERN.search(original):
        return True
    return any(m in reformulated.lower() for m in _ANSWER_PHRASE_MARKERS)


_INVALID_SUBJECTS = {'không', 'chưa', 'tôi', 'bạn', 'em', 'anh', 'chị', 
                      'nó', 'đó', 'này', 'vậy', 'rồi', 'được', 'là', 'có'}

def _extract_subject(text: str) -> str | None:
    """Trích chủ ngữ (tên sản phẩm) từ output LLM, loại bỏ prefix AI."""
    # Bước 1: Xóa tiền tố "Dạ, " / "Vâng, " nếu có
    clean = _AI_PREFIX_PATTERN.sub('', text.strip())
    m = _SUBJECT_PATTERN.match(clean)
    if not m:
        return None
    subject = m.group(1).strip(' *,')
    # Bước 2: Kiểm tra sanity — subject quá dài thì bỏ
    if len(subject) > MAX_SUBJECT_LEN or len(subject) < 3:
        return None
    # Reject stop words / negation words
    if subject.lower().strip() in _INVALID_SUBJECTS:
        return None
    return subject


def _strip_ai_prefix(text: str) -> str:
    """Xóa tiền tố 'Dạ, ' / 'Vâng, ' khỏi nội dung AI khi build history."""
    return _AI_PREFIX_PATTERN.sub('', text).strip()


_HARDWARE_ENTITY_PATTERN = re.compile(
    r'\b(i3|i5|i7|i9|ryzen|rtx|gtx|rx\s*\d+|b760|b850|z790|h610|x670|b650|prime|tuf|gaming|mortar|ventus|gigabyte|msi|asus|asrock|intel|amd|nvidia)\b', 
    re.IGNORECASE
)


def reformulate_query(user_message: str, chat_history: list) -> str:
    if not chat_history:
        return user_message

    # P0.2: Thêm pre-check - Chỉ reformulate khi câu hỏi có đại từ mơ hồ HOẶC thiếu entity linh kiện cụ thể
    if not _PRONOUN_PATTERN.search(user_message) and _HARDWARE_ENTITY_PATTERN.search(user_message):
        return user_message

    try:
        history_str = ""
        last_ai_msg = ""
        _MAX_BOT_HISTORY = 150  # Chống ngộ độc: cắt phần bot để reformulate không bị nhiễu
        for msg in chat_history:
            if getattr(msg, "type", "") == "human":
                history_str += f"Khách: {msg.content}\n"
            elif getattr(msg, "type", "") == "ai":
                # Xóa tiền tố "Dạ, " và cắt ngắn để tránh nhiễu
                bot_text = _strip_ai_prefix(msg.content)
                last_ai_msg = bot_text
                if len(bot_text) > _MAX_BOT_HISTORY:
                    bot_text = bot_text[:_MAX_BOT_HISTORY].rsplit(' ', 1)[0] + "..."
                history_str += f"Bot: {bot_text}\n"

        if not last_ai_msg:
            last_ai_msg = history_str if history_str else user_message

        response = get_reformulate_chain().invoke({
            "user_message": user_message,
            "chat_history_str": history_str,
            "last_ai_msg": last_ai_msg,
        })
        reformulated = response.content.strip()

        if looks_like_full_answer(user_message, reformulated):
            subject = _extract_subject(reformulated)
            if subject:
                # Kiểm tra câu gốc có đại từ để thay thế không
                if _PRONOUN_PATTERN.search(user_message):
                    rebuilt = _PRONOUN_PATTERN.sub(subject, user_message, count=1)
                else:
                    rebuilt = f"{subject} {user_message}"
                if rebuilt != user_message:
                    print(f"[REFORMULATE] Trích chủ ngữ '{subject}' → '{rebuilt}'")
                    return rebuilt
            print(f"[REFORMULATE] LLM trả lời thay vì hỏi, không trích được chủ ngữ hợp lệ. Giữ nguyên câu gốc.")
            print(f"  LLM output: '{reformulated}'")
            return user_message

        print(f"[REFORMULATE] '{user_message}' → '{reformulated}'")
        return reformulated
    except Exception as e:
        print(f"[REFORMULATE] Lỗi, dùng query gốc: {e}")
        return user_message