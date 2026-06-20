from app.core.llm_chains import get_reformulate_chain

def looks_like_full_answer(text: str) -> bool:
    """Phát hiện khi reformulate chain trả lời luôn thay vì chỉ viết lại câu hỏi —
    dấu hiệu: có giá tiền, lời chào, hoặc câu khẳng định kiểu trả lời."""
    markers = ['vnđ', 'giá khoảng', 'tôi sẽ đề xuất', 'dạ,', 'bạn nên chọn']
    return any(m in text.lower() for m in markers)

def reformulate_query(user_message: str, chat_history: list) -> str:
    if not chat_history:
        return user_message
    specific_terms = ['rtx', 'gtx', 'rx', 'i3', 'i5', 'i7', 'i9',
                      'ryzen', 'b760', 'z790', 'x670', 'h610']
    if any(t in user_message.lower() for t in specific_terms):
        return user_message
    try:
        # Chuyển đổi chat_history từ object sang chuỗi văn bản thuần túy
        # để tránh Qwen 1.5B bị kích hoạt chế độ roleplay
        history_str = ""
        for msg in chat_history:
            if getattr(msg, "type", "") == "human":
                history_str += f"Khách: {msg.content}\n"
            elif getattr(msg, "type", "") == "ai":
                history_str += f"Bot: {msg.content}\n"

        response = get_reformulate_chain().invoke({
            "user_message": user_message,
            "chat_history_str": history_str,
        })
        reformulated = response.content.strip()

        # Guard: nếu output trông như câu trả lời hoàn chỉnh
        if looks_like_full_answer(reformulated) or len(reformulated) > max(100, len(user_message) * 3):
            print(f"[REFORMULATE] Bị loại bỏ vì giống câu trả lời. LLM đã sinh ra:\n'{reformulated}'")
            return user_message

        print(f"[REFORMULATE] '{user_message}' → '{reformulated}'")
        return reformulated
    except Exception as e:
        print(f"[REFORMULATE] Lỗi, dùng query gốc: {e}")
        return user_message
