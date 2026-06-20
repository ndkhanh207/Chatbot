import re
from memory.memory_store import save_message
from PCBuilder.pc_build_advisor import extract_budget, PURPOSE_KEYWORD_MAP, find_best_build, format_build_context, _format_approx_million

def handle_pc_build_flow(
    session_id: str, 
    user_message: str, 
    user_message_fixed: str, 
    msg_lower: str, 
    chat_history: list, 
    build_df, 
    is_build_pc: bool
) -> dict | None:
    """
    Xử lý toàn bộ logic liên quan đến PC Build:
    - Bẻ lái intent (Context-aware follow-up)
    - Kế thừa ngân sách, điều chỉnh ngân sách (+/- 30%)
    - Kế thừa mục đích
    - Tìm kiếm bộ PC tốt nhất (trừ các bộ cũ)
    - Format kết quả trả về
    """

    # Context-Aware Follow-up: Nếu khách không gõ từ khóa "build pc" nhưng đang trong mạch tư vấn PC
    if not is_build_pc and chat_history:
        recent_build_context = False
        ai_msg_count = 0
        for msg in reversed(chat_history):
            if getattr(msg, "type", "") == "ai":
                ai_msg_count += 1
                if "[GỢI Ý BỘ PC TỐI ƯU]" in msg.content:
                    recent_build_context = True
                    break
                if ai_msg_count >= 3:  # Cho phép hỏi xen ngang tối đa 3 câu
                    break

        if recent_build_context:
            budget_current = extract_budget(user_message_fixed)
            has_purpose = any(kw in msg_lower for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list)
            is_component_query = re.search(r'\b(cpu|gpu|bo mạch chủ|mainboard|card|chip|vga)\b', msg_lower)
            
            # Phát hiện "câu hỏi về bộ PC đang gợi ý" → KHÔNG trigger build mới
            # Ví dụ: "bộ này chơi được không?", "nó có hỗ trợ không?", "cấu hình này có thể...?"
            is_question_about_current_build = bool(re.search(
                r'\b(bộ này|cái này|nó có|máy này|cấu hình này|bộ đó|cái đó|có thể.*không|chơi được không|có.*không)\b',
                msg_lower
            ))

            # Nếu đổi giá HOẶC đổi mục đích (mà không phải hỏi chi tiết linh kiện,
            # và không phải câu hỏi về bộ PC đang được gợi ý)
            if (budget_current is not None or has_purpose) \
                    and not is_component_query \
                    and not is_question_about_current_build:
                is_build_pc = True

    if not is_build_pc:
        return None

    budget = extract_budget(user_message)
    
    # 1. Kế thừa ngân sách (nếu câu hiện tại không có, mò lại câu cũ)
    if budget is None and chat_history:
        for msg in reversed(chat_history):
            if getattr(msg, "type", "") == "human":
                hist_budget = extract_budget(msg.content)
                if hist_budget is not None:
                    budget = hist_budget
                    
                    # Điều chỉnh nếu khách muốn giá cao hơn/thấp hơn
                    if re.search(r'\b(cao hơn|đắt hơn|mạnh hơn|ngon hơn)\b', msg_lower):
                        budget = int(budget * 1.3) # tăng 30%
                    elif re.search(r'\b(thấp hơn|rẻ hơn|yếu hơn|bèo hơn)\b', msg_lower):
                        budget = int(budget * 0.7) # giảm 30%
                        
                    break

    if budget is None:
        reply = (
            "Dạ em chưa xác định được ngân sách của bạn. "
            "Bạn vui lòng cho em biết tầm giá bạn muốn đầu tư cho bộ PC nhé "
            "(ví dụ: 20 triệu, 30 triệu...)"
        )
        save_message(session_id, user_message, reply)
        return {"chatbot_reply": reply}

    # 2. Kế thừa mục đích (nếu câu hiện tại chỉ đổi giá mà quên ghi mục đích)
    current_has_purpose = any(kw in msg_lower for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list)
    combined_message_for_purpose = user_message
    
    if not current_has_purpose and chat_history:
        for msg in reversed(chat_history):
            if getattr(msg, "type", "") == "human":
                if any(kw in msg.content.lower() for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list):
                    combined_message_for_purpose += " " + msg.content
                    break

    # Tìm các bộ PC đã gợi ý trước đó để tránh lặp lại
    exclude_builds = []
    if chat_history:
        for msg in reversed(chat_history):
            if getattr(msg, "type", "") == "ai":
                m = re.search(r'Mã bộ\s*:\s*(BUILD-\d+)', msg.content)
                if m:
                    exclude_builds.append(m.group(1).strip())

    best_build = find_best_build(budget, combined_message_for_purpose, build_df, exclude_builds=exclude_builds)

    if best_build is None:
        reply = (
            "Dạ, hiện tại bên em không tìm được bộ PC nào phù hợp với "
            f"ngân sách và mục đích của bạn. "
            "Bạn có thể điều chỉnh ngân sách hoặc cho em biết thêm nhu cầu "
            "cụ thể để em tư vấn thêm nhé!"
        )
        save_message(session_id, user_message, reply)
        return {"chatbot_reply": reply}

    build_context = format_build_context(best_build)

    # ====== DEBUG PC BUILD ======
    print("\n" + "═" * 60)
    print(f"🔍 [HỆ THỐNG DEBUG CHAT] - Session ID: {session_id}")
    print(f"🔹 1. Câu hỏi gốc của khách: '{user_message}'")
    print(f"🔹 2. Intent: BUILD PC")
    print(f"🔹 3. Ngân sách nhận diện: {budget} VNĐ")
    print(f"🔹 4. Bộ PC tìm thấy: {best_build.get('BuildID', 'N/A')}")
    print(f"🔹 5. Nội dung [context] nhét vào miệng Bot:\n{build_context}")
    print("═" * 60 + "\n")

    # Format lại kết quả bằng Python thuần nhưng dùng văn phong tự nhiên
    cpu_model = best_build.get('CPU_Model', 'N/A')
    cpu_price = _format_approx_million(best_build.get('Component_Price_CPU', 0))
    gpu_model = best_build.get('GPU_Model', 'N/A')
    gpu_price = _format_approx_million(best_build.get('Component_Price_GPU', 0))
    main_model = best_build.get('Motherboard_Model', 'N/A')
    main_price = _format_approx_million(best_build.get('Component_Price_Motherboard', 0))
    total_price = _format_approx_million(best_build.get('Total_Price', 0))
    budget_str = _format_approx_million(budget)
    build_id = best_build.get('BuildID', 'N/A')
    
    # Nội suy mục đích từ câu hỏi
    purpose_str = "sử dụng"
    for kw in ['văn phòng', 'chơi game aaa', 'chơi game', 'render', 'đồ họa', 'lập trình', 'ai', 'stream']:
        if kw in combined_message_for_purpose.lower():
            purpose_str = kw
            break

    assembly_price = _format_approx_million(best_build.get('Assembly_Fee', 0.2e6))

    reply = (
        f"[GỢI Ý BỘ PC TỐI ƯU]\n"
        f"- Mã bộ: {build_id}\n\n"
        f"Xin chào, tôi rất vui được giúp bạn xây dựng một máy tính để {purpose_str} hiệu quả! "
        f"Bạn muốn sử dụng bộ PC này cho {purpose_str} và có ngân sách khoảng {budget_str}.\n\n"
        f"Bộ PC của bạn sẽ bao gồm các thành phần sau:\n\n"
        f"- CPU: {cpu_model}, giá {cpu_price}\n"
        f"- GPU: {gpu_model}, giá {gpu_price}\n"
        f"- Mainboard: {main_model}, giá {main_price}\n"
        f"- Phí lắp ráp: {assembly_price}\n\n"
        f"Tổng cộng chi phí cho các thành phần này là khoảng {total_price}."
    )
    
    save_message(session_id, user_message, reply)
    return {"chatbot_reply": reply}
