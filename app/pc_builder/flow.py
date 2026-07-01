import re
from app.memory.memory_store import save_message

# Import Facades (để giữ nguyên logic không làm gãy code)
from .constants import (
    BEST_KEYWORDS, CHEAPEST_KEYWORDS, PURPOSE_KEYWORD_MAP
)
from .extractor import (
    extract_budget, extract_quantity, extract_brand_filter,
    extract_component_filter, extract_explicit_build_id, infer_purpose,
    is_reset_intent
)
from .history import (
    ai_asked_for_budget, ai_asked_for_purpose, is_build_context_active,
    get_exclude_builds, get_last_build_id, inherit_budget, inherit_quantity,
    inherit_component_intent
)
from .formatter import format_approx_million, format_build_context, format_reply_body

from app.pc_builder.advisor import find_best_build


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

    # ── ƯU TIÊN CAO NHẤT: User nhắc thẳng mã BuildID cụ thể ──
    explicit_build_id = extract_explicit_build_id(user_message)
    if explicit_build_id:
        if build_df is not None and not build_df.empty:
            rows = build_df[build_df['BuildID'].str.upper() == explicit_build_id.upper()]
        else:
            rows = None

        if rows is not None and not rows.empty:
            matched_build = rows.iloc[0].to_dict()
            return _answer_about_specific_build(user_uid, session_id, user_message, matched_build)
        else:
            reply = (
                f"Dạ, em không tìm thấy bộ PC nào có mã **{explicit_build_id}** "
                "trong hệ thống ạ. Bạn kiểm tra lại mã giúp em nhé!"
            )
            save_message(user_uid, session_id, user_message, reply)
            return {'chatbot_reply': reply}

    wants_cheapest = any(kw in msg_lower for kw in CHEAPEST_KEYWORDS)
    wants_best     = any(kw in msg_lower for kw in BEST_KEYWORDS)

    # ── BUG 3: Context-Aware Follow-up ──
    # Nếu AI vừa hỏi ngân sách hoặc mục đích, câu tiếp theo trả lời đúng trọng tâm là đủ trigger
    if not is_build_pc and chat_history:
        asked_budget = ai_asked_for_budget(chat_history)
        asked_purpose = ai_asked_for_purpose(chat_history)
        
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
        exclude_builds   = get_exclude_builds(chat_history)
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
        inherited_budget = inherit_budget(msg_lower, chat_history)
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
            budget = inherit_budget(msg_lower, chat_history)

    # ── BUG 1: Ngân sách âm hoặc quá nhỏ ──
    if budget is not None and budget < 10_000_000:
        if budget <= 0:
            # Dùng lại bộ cuối cùng từ lịch sử
            last_build_id = get_last_build_id(chat_history)
            if last_build_id and build_df is not None:
                rows = build_df[build_df['BuildID'] == last_build_id]
                if not rows.empty:
                    best_build = rows.iloc[0].to_dict()
                    reply = (
                        f"Ngân sách không hợp lệ ạ! Em hiển thị lại bộ PC trước đó cho bạn tham khảo:\n\n"
                        + format_reply_body(best_build, 0, 'sử dụng')
                    )
                    save_message(user_uid, session_id, user_message, reply)
                    return {'chatbot_reply': reply}
            reply = "Dạ, ngân sách không hợp lệ ạ. Bạn vui lòng nhập lại tầm giá mong muốn nhé!"
            save_message(user_uid, session_id, user_message, reply)
            return {'chatbot_reply': reply}
        else:
            # Ngân sách từ 1đ đến 9.999.999đ
            reply = (
                f"Dạ ngân sách {format_approx_million(budget)} hơi thấp ạ. "
                "Hiện tại các bộ PC bên em đang phân phối có giá từ 10 triệu trở lên. "
                "Bạn cân nhắc nâng thêm chút ngân sách nhé!"
            )
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
    
    # [FIX]: Kế thừa số lượng từ lịch sử nếu câu hiện tại không đề cập
    if quantity == 1 and chat_history:
        quantity = inherit_quantity(chat_history)
        
    if quantity > 1 and budget is not None and budget > 0:
        budget_per_unit = budget // quantity
        # Đảm bảo budget mỗi bộ hợp lý (>= 10 triệu do data cửa hàng)
        if budget_per_unit < 10_000_000:
            reply = (
                f"Dạ, với tổng ngân sách {format_approx_million(budget)} cho {quantity} bộ, "
                f"mỗi bộ chỉ có ~{format_approx_million(budget_per_unit)}. "
                "Hiện tại cấu hình PC bên em phân phối có giá thấp nhất từ 10 triệu/bộ ạ. "
                "Bạn có thể tăng ngân sách hoặc giảm số lượng không?"
            )
            save_message(user_uid, session_id, user_message, reply)
            return {'chatbot_reply': reply}
        budget = budget_per_unit

    # ── BUG 5 & 6: Lấy brand filter và component filter (CÓ KẾ THỪA LỊCH SỬ) ──
    brand_filter = extract_brand_filter(search_query)
    component_filter = extract_component_filter(search_query)

    if chat_history and not is_reset_intent(user_message):
        print("\n=== 🔍 [DEBUG PC BUILDER] KIỂM TRA LỊCH SỬ ĐỂ KẾ THỪA LINH KIỆN ===")
        inherited = inherit_component_intent(chat_history, max_turns=4)
        
        # Merge (ưu tiên tin nhắn hiện tại, kế thừa chỉ điền vào chỗ trống)
        if not component_filter.get('cpu_model') and inherited.get('cpu_model'):
            component_filter['cpu_model'] = inherited['cpu_model']
        if not component_filter.get('gpu_model') and inherited.get('gpu_model'):
            component_filter['gpu_model'] = inherited['gpu_model']
        if not brand_filter.get('cpu_brand') and inherited.get('cpu_brand'):
            brand_filter['cpu_brand'] = inherited['cpu_brand']
        if not brand_filter.get('gpu_brand') and inherited.get('gpu_brand'):
            brand_filter['gpu_brand'] = inherited['gpu_brand']
        print("====================================================\n")

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
            purpose_str = infer_purpose(combined_message_for_purpose)
            reply = (
                f"Dạ để build bộ máy tối ưu cho nhu cầu {purpose_str}, "
                "bạn dự định đầu tư khoảng bao nhiêu tiền ạ? (ví dụ: 20 triệu, 30 triệu...)"
            )
        save_message(user_uid, session_id, user_message, reply)
        return {'chatbot_reply': reply}

    if budget is not None and not has_final_purpose and not has_specific_component:
        reply = (
            f"Dạ với ngân sách khoảng {format_approx_million(budget)}, em có thể ráp được nhiều cấu hình tối ưu "
            "cho các mục đích khác nhau. Bạn dự định dùng máy chủ yếu để làm gì ạ? "
            "(ví dụ: chơi game AAA, văn phòng, làm đồ họa 3D, hay lập trình...)"
        )
        save_message(user_uid, session_id, user_message, reply)
        return {'chatbot_reply': reply}

    exclude_builds = get_exclude_builds(chat_history)

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

    build_context = format_build_context(best_build)
    purpose_str = infer_purpose(combined_message_for_purpose)

    return _build_reply(user_uid, session_id, user_message, best_build, budget, purpose_str, quantity)

def _build_reply(user_uid: str, session_id: str, user_message: str, best_build: dict,
                 budget: int, purpose_str: str, quantity: int = 1) -> dict:
    """Build và lưu câu trả lời hoàn chỉnh."""
    reply = format_reply_body(best_build, budget, purpose_str, quantity)
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

def _answer_about_specific_build(user_uid: str, session_id: str, user_message: str, build: dict) -> dict:
    """Trả lời câu hỏi về một bộ PC cụ thể mà user chỉ định mã Build."""
    from app.utils.model_utils import get_ollama_model
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate

    build_context = format_build_context(build)

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Bạn là chuyên gia tư vấn linh kiện máy tính tại cửa hàng. "
         "Dưới đây là thông số của bộ PC mà khách đang hỏi tới:\n\n{build_context}\n\n"
         "Hãy trả lời câu hỏi của khách hàng về bộ PC này thật ngắn gọn, chính xác, "
         "súc tích và thân thiện, dựa hoàn toàn vào thông số trên. "
         "Không được tự bịa ra thông số không có trong bộ PC."),
        ("human", "{user_message}")
    ])
    llm = ChatOllama(model=get_ollama_model(), temperature=0.1)
    chain = prompt | llm

    try:
        res = chain.invoke({"build_context": build_context, "user_message": user_message})
        reply = res.content.strip()
    except Exception:
        reply = build_context + "\n\nBạn có muốn em tư vấn thêm về bộ PC này không ạ?"

    save_message(user_uid, session_id, user_message, reply)
    return {'chatbot_reply': reply}