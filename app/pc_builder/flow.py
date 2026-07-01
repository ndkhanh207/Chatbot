import re
from app.memory.memory_store import save_message
from app.pc_builder.advisor import (
    extract_budget, extract_quantity, extract_brand_filter, extract_component_filter,
    PURPOSE_KEYWORD_MAP, find_best_build, format_build_context, _format_approx_million,
)

# ──────────────────────────────────────────────
# Từ khóa "tốt nhất / rẻ nhất"
# ──────────────────────────────────────────────
BEST_KEYWORDS    = ['tốt nhất', 'ngon nhất', 'mạnh nhất', 'đỉnh nhất', 'cao cấp nhất']
CHEAPEST_KEYWORDS = ['rẻ nhất', 'giá thấp nhất', 'thấp nhất', 'tiết kiệm nhất', 'bèo nhất']

# Các từ khóa nhận diện câu hỏi từ AI
AI_BUDGET_KEYWORDS = ['ngân sách', 'tầm giá', 'bao nhiêu tiền', 'đầu tư cho bộ pc', 'dự định đầu tư']
AI_PURPOSE_KEYWORDS = ['để làm gì', 'mục đích gì', 'nhu cầu của bạn']
AI_BUILD_CONTEXT_KEYWORDS = AI_BUDGET_KEYWORDS + AI_PURPOSE_KEYWORDS + ['tư vấn bộ pc']


def _ai_asked_for_budget(chat_history: list) -> bool:
    """Kiểm tra xem AI vừa hỏi ngân sách ở tin nhắn trước không."""
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai':
            content = msg.content.lower()
            if any(kw in content for kw in AI_BUDGET_KEYWORDS):
                return True
            return False  # Tin AI gần nhất không hỏi budget
    return False


def _ai_asked_for_purpose(chat_history: list) -> bool:
    """Kiểm tra xem AI vừa hỏi nhu cầu/mục đích ở tin nhắn trước không."""
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai':
            content = msg.content.lower()
            if any(kw in content for kw in AI_PURPOSE_KEYWORDS):
                return True
            return False
    return False
def _is_build_context_active(chat_history: list) -> bool:
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


def handle_pc_build_flow(
    user_uid: str,
    session_id: str,
    user_message: str,
    user_message_fixed: str,
    msg_lower: str,
    search_query: str,
    chat_history: list,
    build_df,
    is_build_pc: bool,
) -> dict | None:
    """
    Xử lý toàn bộ logic liên quan đến PC Build:
    - Bẻ lái intent (Context-aware follow-up)
    - Xử lý "rẻ nhất / tốt nhất"
    - Kế thừa ngân sách, điều chỉnh (+/- 30%), số âm
    - Xử lý số lượng bộ (tiệm net)
    - Filter theo brand (Intel/AMD/NVIDIA) và model cụ thể
    - Báo rõ nếu component không có trong DB
    """

    wants_cheapest = any(kw in msg_lower for kw in CHEAPEST_KEYWORDS)
    wants_best     = any(kw in msg_lower for kw in BEST_KEYWORDS)

    # ── BUG 3: Context-Aware Follow-up ──
    # Nếu AI vừa hỏi ngân sách hoặc mục đích, câu tiếp theo trả lời đúng trọng tâm là đủ trigger
    if not is_build_pc and chat_history:
        asked_budget = _ai_asked_for_budget(chat_history)
        asked_purpose = _ai_asked_for_purpose(chat_history)
        
        if asked_budget and (extract_budget(user_message) is not None or wants_cheapest):
            is_build_pc = True
        elif asked_purpose:
            has_purpose = any(kw in msg_lower for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list)
            if has_purpose:
                is_build_pc = True

    # Context-Aware Follow-up chung: đang trong mạch tư vấn PC
    if not is_build_pc and chat_history:
        recent_build_context = False
        ai_msg_count = 0
        for msg in reversed(chat_history):
            if getattr(msg, 'type', '') == 'ai':
                ai_msg_count += 1
                if '[GỢI Ý BỘ PC TỐI ƯU]' in msg.content:
                    recent_build_context = True
                    break
                if ai_msg_count >= 3:
                    break

        if recent_build_context:
            budget_current = extract_budget(user_message_fixed)
            has_purpose = any(kw in msg_lower for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list)
            is_component_query = re.search(r'\b(cpu|gpu|bo mạch chủ|mainboard|card|chip|vga)\b', msg_lower)

            # Có muốn tăng giảm giá không?
            wants_adjustment = bool(re.search(r'\b(cao hơn|đắt hơn|mạnh hơn|ngon hơn|thấp hơn|rẻ hơn|yếu hơn|bèo hơn)\b', msg_lower))

            # Không trigger PC Build mới nếu đang hỏi về bộ hiện tại
            is_question_about_current_build = bool(re.search(
                r'\b(bộ này|cái này|nó có|máy này|cấu hình này|bộ đó|cái đó|có thể.*không|chơi được không|có.*không)\b',
                msg_lower
            ))

            if (budget_current is not None or has_purpose or wants_cheapest or wants_best or wants_adjustment) \
                    and not is_component_query \
                    and not is_question_about_current_build:
                is_build_pc = True

            # GỌI MINI-CHAIN TRẢ LỜI CÂU HỎI VỀ BỘ PC HIỆN TẠI
            if is_question_about_current_build and not is_build_pc:
                return _answer_about_current_build(user_uid, session_id, user_message, chat_history)

    if not is_build_pc:
        return None

    # ── BUG 4: Xử lý "rẻ nhất" ──
    if wants_cheapest:
        brand_filter     = extract_brand_filter(user_message)
        component_filter = extract_component_filter(user_message)
        exclude_builds   = _get_exclude_builds(chat_history)
        best_build = find_best_build(
            budget=0,
            user_message=user_message,
            build_df=build_df,
            exclude_builds=exclude_builds,
            brand_filter=brand_filter,
            component_filter=component_filter,
            find_cheapest=True,
        )
        if best_build is None:
            reply = "Dạ, em không tìm được bộ PC nào phù hợp trong kho ạ!"
            save_message(user_uid, session_id, user_message, reply)
            return {'chatbot_reply': reply}
        return _build_reply(user_uid, session_id, user_message, best_build, 0, 'rẻ nhất')

    # ── BUG 4: Xử lý "tốt nhất" — hỏi ngân sách nếu chưa có ──
    if wants_best:
        # Kiểm tra có ngân sách trong lịch sử không
        inherited_budget = _inherit_budget(msg_lower, chat_history)
        if inherited_budget is None:
            reply = (
                "Dạ, để tìm bộ PC tốt nhất cho bạn, "
                "em cần biết ngân sách bạn muốn đầu tư là bao nhiêu ạ? "
                "(ví dụ: 30 triệu, 50 triệu...)"
            )
            save_message(user_uid, session_id, user_message, reply)
            return {'chatbot_reply': reply}
        # Có ngân sách → tìm bộ tốt nhất trong tầm giá đó
        budget = inherited_budget

    else:
        budget = extract_budget(user_message)
        if budget is None:
            budget = _inherit_budget(msg_lower, chat_history)

    # ── BUG 1: Ngân sách âm hoặc quá nhỏ ──
    if budget is not None and budget <= 0:
        # Dùng lại bộ cuối cùng từ lịch sử
        last_build_id = _get_last_build_id(chat_history)
        if last_build_id and build_df is not None:
            rows = build_df[build_df['BuildID'] == last_build_id]
            if not rows.empty:
                best_build = rows.iloc[0].to_dict()
                reply = (
                    f"Ngân sách không hợp lệ ạ! Em hiển thị lại bộ PC trước đó cho bạn tham khảo:\n\n"
                    + _format_reply_body(best_build, 0, 'sử dụng')
                )
                save_message(user_uid, session_id, user_message, reply)
                return {'chatbot_reply': reply}
        reply = "Dạ, ngân sách không hợp lệ ạ. Bạn vui lòng nhập lại tầm giá mong muốn nhé!"
        save_message(user_uid, session_id, user_message, reply)
        return {'chatbot_reply': reply}

    # ── FEATURE: Kế thừa và trích xuất Mục đích (Nhu cầu) ──
    has_final_purpose = any(kw in msg_lower for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list)
    combined_message_for_purpose = user_message
    
    if not has_final_purpose and chat_history:
        for msg in reversed(chat_history):
            if getattr(msg, 'type', '') == 'human':
                if any(kw in msg.content.lower() for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list):
                    combined_message_for_purpose += ' ' + msg.content
                    has_final_purpose = True
                    break

    # ── BUG 2: Số lượng bộ PC ("10 bộ giá 200 triệu") ──
    quantity = extract_quantity(user_message)
    if quantity > 1 and budget is not None and budget > 0:
        budget_per_unit = budget // quantity
        # Đảm bảo budget mỗi bộ hợp lý (>= 5 triệu)
        if budget_per_unit < 5_000_000:
            reply = (
                f"Dạ, với tổng ngân sách {_format_approx_million(budget)} cho {quantity} bộ, "
                f"mỗi bộ chỉ có ~{_format_approx_million(budget_per_unit)} — quá thấp để build được ạ. "
                "Bạn có thể tăng ngân sách hoặc giảm số lượng không?"
            )
            save_message(user_uid, session_id, user_message, reply)
            return {'chatbot_reply': reply}
        budget = budget_per_unit

    # ── BUG 5 & 6: Lấy brand filter và component filter (CÓ KẾ THỪA LỊCH SỬ) ──
    # Dùng search_query (đã được LLM reformulate) thay vì user_message gốc để tận dụng khả năng hiểu ngữ cảnh của LLM
    brand_filter = extract_brand_filter(search_query)
    component_filter = extract_component_filter(search_query)

    if chat_history and _is_build_context_active(chat_history):
        print("\n=== 🔍 [DEBUG PC BUILDER] KIỂM TRA LỊCH SỬ ĐỂ KẾ THỪA ===")
        for msg in reversed(chat_history):
            if getattr(msg, 'type', '') == 'human':
                hist_brand = extract_brand_filter(msg.content)
                hist_comp = extract_component_filter(msg.content)
                print(f"👉 Xét tin nhắn cũ: '{msg.content}'")
                print(f"   - Brand trích xuất: {hist_brand}")
                print(f"   - Component trích xuất: {hist_comp}")

                # Kế thừa brand nếu hiện tại đang rỗng
                if not brand_filter.get('cpu_brand') and hist_brand.get('cpu_brand'):
                    brand_filter['cpu_brand'] = hist_brand['cpu_brand']
                    print(f"   ✅ Kế thừa CPU Brand: {brand_filter['cpu_brand']}")
                if not brand_filter.get('gpu_brand') and hist_brand.get('gpu_brand'):
                    brand_filter['gpu_brand'] = hist_brand['gpu_brand']
                    print(f"   ✅ Kế thừa GPU Brand: {brand_filter['gpu_brand']}")
                if not brand_filter.get('any_brand') and hist_brand.get('any_brand'):
                    brand_filter['any_brand'] = hist_brand['any_brand']
                    print(f"   ✅ Kế thừa Any Brand: {brand_filter['any_brand']}")

                # Kế thừa component nếu hiện tại đang rỗng
                if not component_filter.get('cpu_model') and hist_comp.get('cpu_model'):
                    component_filter['cpu_model'] = hist_comp['cpu_model']
                    print(f"   ✅ Kế thừa CPU Model: {component_filter['cpu_model']}")
                if not component_filter.get('gpu_model') and hist_comp.get('gpu_model'):
                    component_filter['gpu_model'] = hist_comp['gpu_model']
                    print(f"   ✅ Kế thừa GPU Model: {component_filter['gpu_model']}")
        print("====================================================\n")
    else:
        print("\n=== 🚫 [DEBUG PC BUILDER] BỎ QUA KẾ THỪA VÌ KHÔNG TRONG LUỒNG BUILD ===")


    has_specific_component = bool(component_filter.get('cpu_model') or component_filter.get('gpu_model'))

    # ── LOGIC CHÍNH: Ưu tiên hỏi Nhu cầu / Ngân sách nếu thiếu ──
    if budget is None and not has_final_purpose and not has_specific_component:
        reply = (
            "Dạ, để em tư vấn bộ PC chuẩn nhất, bạn cho em biết bạn dùng máy chủ yếu "
            "để làm gì (chơi game, làm đồ họa...) và tầm giá khoảng bao nhiêu nhé!"
        )
        save_message(user_uid, session_id, user_message, reply)
        return {'chatbot_reply': reply}

    if budget is None and (has_final_purpose or has_specific_component):
        if has_specific_component and not has_final_purpose:
            comp_name = component_filter.get('cpu_model') or component_filter.get('gpu_model')
            reply = (
                f"Dạ để build bộ máy có {comp_name.upper()}, "
                "bạn dự định đầu tư khoảng bao nhiêu tiền ạ? (ví dụ: 20 triệu, 30 triệu...)"
            )
        else:
            purpose_str = _infer_purpose(combined_message_for_purpose)
            reply = (
                f"Dạ để build bộ máy tối ưu cho nhu cầu {purpose_str}, "
                "bạn dự định đầu tư khoảng bao nhiêu tiền ạ? (ví dụ: 20 triệu, 30 triệu...)"
            )
        save_message(user_uid, session_id, user_message, reply)
        return {'chatbot_reply': reply}

    if budget is not None and not has_final_purpose and not has_specific_component:
        reply = (
            f"Dạ với ngân sách khoảng {_format_approx_million(budget)}, em có thể ráp được nhiều cấu hình tối ưu "
            "cho các mục đích khác nhau. Bạn dự định dùng máy chủ yếu để làm gì ạ? "
            "(ví dụ: chơi game AAA, văn phòng, làm đồ họa 3D, hay lập trình...)"
        )
        save_message(user_uid, session_id, user_message, reply)
        return {'chatbot_reply': reply}

    exclude_builds = _get_exclude_builds(chat_history)

    best_build = find_best_build(
        budget=budget,
        user_message=combined_message_for_purpose,
        build_df=build_df,
        exclude_builds=exclude_builds,
        brand_filter=brand_filter,
        component_filter=component_filter,
    )

    # ── BUG 6: Nếu filter component không tìm thấy → báo rõ ràng ──
    if best_build is None:
        comp = component_filter or {}
        gpu_req = comp.get('gpu_model')
        cpu_req = comp.get('cpu_model')
        brand   = brand_filter or {}

        if gpu_req:
            reply = (
                f"Dạ, hiện bên em chưa có bộ PC nào sử dụng GPU **{gpu_req.upper()}** trong kho ạ. "
                "Bạn có muốn em gợi ý bộ PC dùng GPU gần nhất không?"
            )
        elif cpu_req:
            reply = (
                f"Dạ, hiện bên em chưa có bộ PC nào sử dụng CPU **{cpu_req.upper()}** phù hợp với ngân sách này ạ. "
                "Bạn có muốn thử ngân sách cao hơn không?"
            )
        elif brand.get('cpu_brand') or brand.get('gpu_brand'):
            brand_name = brand.get('cpu_brand') or brand.get('gpu_brand')
            reply = (
                f"Dạ, em không tìm được bộ PC {brand_name} nào phù hợp với ngân sách của bạn ạ. "
                "Bạn thử điều chỉnh ngân sách hoặc bỏ yêu cầu hãng nhé!"
            )
        else:
            reply = (
                "Dạ, hiện tại bên em không tìm được bộ PC nào phù hợp với "
                "ngân sách và mục đích của bạn. "
                "Bạn có thể điều chỉnh ngân sách hoặc cho em biết thêm nhu cầu cụ thể nhé!"
            )
        save_message(user_uid, session_id, user_message, reply)
        return {'chatbot_reply': reply}

    # ── Debug log ──
    build_context = format_build_context(best_build)
    print('\n' + '═' * 60)
    print(f"🔍 [HỆ THỐNG DEBUG CHAT] - Session ID: {session_id}")
    print(f"🔹 1. Câu hỏi gốc của khách: '{user_message}'")
    print(f"🔹 2. Intent: BUILD PC")
    print(f"🔹 3. Ngân sách nhận diện: {budget} VNĐ | Số lượng: {quantity}")
    print(f"🔹 4. Bộ PC tìm thấy: {best_build.get('BuildID', 'N/A')}")
    print(f"🔹 5. Nội dung [context] nhét vào miệng Bot:\n{build_context}")
    print('═' * 60 + '\n')

    # Nội suy mục đích
    purpose_str = _infer_purpose(combined_message_for_purpose)

    return _build_reply(user_uid, session_id, user_message, best_build, budget, purpose_str, quantity)


# ──────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────
def _get_exclude_builds(chat_history: list) -> list:
    """Lấy danh sách BuildID đã gợi ý để tránh lặp."""
    exclude = []
    if chat_history:
        for msg in reversed(chat_history):
            if getattr(msg, 'type', '') == 'ai':
                m = re.search(r'Mã bộ\s*:\s*(BUILD-\d+)', msg.content)
                if m:
                    exclude.append(m.group(1).strip())
    return exclude


def _get_last_build_id(chat_history: list) -> str | None:
    """Lấy BuildID gần nhất từ lịch sử."""
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai':
            m = re.search(r'Mã bộ\s*:\s*(BUILD-\d+)', msg.content)
            if m:
                return m.group(1).strip()
    return None


def _inherit_budget(msg_lower: str, chat_history: list) -> int | None:
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


def _infer_purpose(combined_msg: str) -> str:
    """Nội suy mục đích từ câu hỏi."""
    msg_lower = combined_msg.lower()
    for kw in ['văn phòng', 'tiệm net', 'chơi game aaa', 'chơi game', 'render',
               'đồ họa', 'lập trình', 'deep learning', 'ai', 'stream']:
        if kw in msg_lower:
            return kw
    return 'sử dụng'


def _format_reply_body(best_build: dict, budget: int, purpose_str: str, quantity: int = 1) -> str:
    """Format phần thân câu trả lời."""
    cpu_model      = best_build.get('CPU_Model', 'N/A')
    cpu_price      = _format_approx_million(best_build.get('Component_Price_CPU', 0))
    gpu_model      = best_build.get('GPU_Model', 'N/A')
    gpu_price      = _format_approx_million(best_build.get('Component_Price_GPU', 0))
    main_model     = best_build.get('Motherboard_Model', 'N/A')
    main_price     = _format_approx_million(best_build.get('Component_Price_Motherboard', 0))
    total_price    = _format_approx_million(best_build.get('Total_Price', 0))
    assembly_price = _format_approx_million(best_build.get('Assembly_Fee', 200_000))
    build_id       = best_build.get('BuildID', 'N/A')
    budget_str     = _format_approx_million(budget) if budget > 0 else 'rẻ nhất'

    qty_note = f" (×{quantity} bộ = {_format_approx_million(best_build.get('Total_Price', 0) * quantity)})" \
               if quantity > 1 else ""

    return (
        f"[GỢI Ý BỘ PC TỐI ƯU]\n"
        f"- Mã bộ: {build_id}\n\n"
        f"Xin chào, tôi rất vui được giúp bạn xây dựng một máy tính để {purpose_str} hiệu quả! "
        f"Bạn muốn sử dụng bộ PC này cho {purpose_str} và có ngân sách khoảng {budget_str}.\n\n"
        f"Bộ PC của bạn sẽ bao gồm các thành phần sau:\n\n"
        f"- CPU: {cpu_model}, giá {cpu_price}\n"
        f"- GPU: {gpu_model}, giá {gpu_price}\n"
        f"- Mainboard: {main_model}, giá {main_price}\n"
        f"- Phí lắp ráp: {assembly_price}\n\n"
        f"Tổng cộng chi phí cho các thành phần này là khoảng {total_price}{qty_note}."
    )


def _build_reply(user_uid: str, session_id: str, user_message: str, best_build: dict,
                 budget: int, purpose_str: str, quantity: int = 1) -> dict:
    """Build và lưu câu trả lời hoàn chỉnh."""
    reply = _format_reply_body(best_build, budget, purpose_str, quantity)
    save_message(user_uid, session_id, user_message, reply)
    return {'chatbot_reply': reply}

def _answer_about_current_build(user_uid: str, session_id: str, user_message: str, chat_history: list) -> dict:
    """Trả lời các câu hỏi follow-up về bộ PC vừa được build bằng cách gửi thẳng context cho LLM."""
    from app.utils.model_utils import get_ollama_model
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    
    last_build_msg = ""
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai' and '[GỢI Ý BỘ PC TỐI ƯU]' in msg.content:
            last_build_msg = msg.content
            break
            
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Bạn là chuyên gia tư vấn linh kiện máy tính tại cửa hàng. Dưới đây là thông số bộ PC mà bạn vừa gợi ý cho khách:\n\n{last_build}\n\nHãy trả lời câu hỏi của khách hàng về bộ PC này một cách thật ngắn gọn, chính xác, súc tích và thân thiện. Không được tự bịa ra thông số không có trong bộ PC."),
        ("human", "{user_message}")
    ])
    llm = ChatOllama(model=get_ollama_model(), temperature=0.1)
    chain = prompt | llm
    
    try:
        res = chain.invoke({"last_build": last_build_msg, "user_message": user_message})
        reply = res.content.strip()
    except Exception as e:
        reply = "Dạ bộ PC này rất ngon trong tầm giá ạ! Bạn có muốn lấy bộ này luôn không?"
        
    save_message(user_uid, session_id, user_message, reply)
    return {'chatbot_reply': reply}

