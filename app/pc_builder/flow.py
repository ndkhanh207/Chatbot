import re
from app.memory.memory_store import save_message

from .constants import (
    BEST_KEYWORDS, CHEAPEST_KEYWORDS, PURPOSE_KEYWORD_MAP
)
from .extractor import (
    extract_budget, extract_quantity, extract_brand_filter,
    extract_component_filter, extract_explicit_build_id, infer_purpose,
    is_reset_intent, extract_upgrade_component
)
from .history import (
    ai_asked_for_budget, ai_asked_for_purpose, is_build_context_active,
    get_exclude_builds, get_last_build_id, inherit_budget, inherit_quantity,
    inherit_component_intent
)
from .formatter import format_approx_million, format_build_context, format_reply_body

from app.pc_builder.advisor import find_best_build
from app.pc_builder.preset.presets import get_preset_reply


BUILD_REPLY_HEADER = '[GỢI Ý BỘ PC TỐI ƯU]'


def _apply_upgrade_to_filter(component_filter: dict, upgrade_info: dict) -> None:
    """Merge upgrade CPU/GPU vào component_filter nếu chưa có."""
    if upgrade_info.get('is_upgrade'):
        if upgrade_info.get('cpu_model') and not component_filter.get('cpu_model'):
            component_filter['cpu_model'] = upgrade_info['cpu_model']
        if upgrade_info.get('gpu_model') and not component_filter.get('gpu_model'):
            component_filter['gpu_model'] = upgrade_info['gpu_model']


def _resolve_context_override(is_build_pc: bool, user_message: str, user_message_fixed: str, msg_lower: str, chat_history: list) -> tuple[bool, bool, dict | None]:
    """
    Context-Aware fallback override logic.
    Returns: (is_build_pc, is_question_about_current_build, early_reply)
    """
    if is_build_pc or not chat_history:
        return is_build_pc, False, None

    asked_budget = ai_asked_for_budget(chat_history)
    asked_purpose = ai_asked_for_purpose(chat_history)
    wants_cheapest = any(kw in msg_lower for kw in CHEAPEST_KEYWORDS)
    has_purpose = any(kw in msg_lower for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list)
    
    if asked_budget and (extract_budget(user_message) is not None or wants_cheapest):
        print(f"⚠️ [FALLBACK OVERRIDE] Context-Aware: Khách đang trả lời ngân sách, ép luồng BUILD_PC.")
        is_build_pc = True
    elif asked_purpose and has_purpose:
        print(f"⚠️ [FALLBACK OVERRIDE] Context-Aware: Khách đang trả lời mục đích, ép luồng BUILD_PC.")
        is_build_pc = True

    recent_build_context = False
    ai_msg_count = 0
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai':
            ai_msg_count += 1
            if BUILD_REPLY_HEADER in msg.content:
                recent_build_context = True
                break
            if ai_msg_count >= 3:
                break

    is_question_about_current_build = False
    if recent_build_context:
        budget_current = extract_budget(user_message_fixed)
        is_component_query = re.search(r'\b(cpu|gpu|bo mạch chủ|mainboard|card|chip|vga)\b', msg_lower)
        wants_adjustment = bool(re.search(r'\b(cao hơn|đắt hơn|mạnh hơn|ngon hơn|thấp hơn|rẻ hơn|yếu hơn|bèo hơn)\b', msg_lower))
        wants_best = any(kw in msg_lower for kw in BEST_KEYWORDS)

        is_question_about_current_build = bool(re.search(
            r'\b(bộ này|cái này|nó có|máy này|cấu hình này|bộ đó|cái đó|có thể.*không|chơi được không|có.*không)\b',
            msg_lower
        ))

        if (budget_current is not None or has_purpose or wants_cheapest or wants_best or wants_adjustment) \
                and not is_component_query \
                and not is_question_about_current_build:
            print(f"⚠️ [FALLBACK OVERRIDE] Context-Aware: Có keyword điều chỉnh PC đang build, ép luồng BUILD_PC.")
            is_build_pc = True

    return is_build_pc, is_question_about_current_build, None


def _resolve_budget_and_quantity(budget: int | None, user_message: str, msg_lower: str, quantity: int, wants_best: bool, chat_history: list, user_uid: str, session_id: str, build_df) -> tuple[int | None, int, dict | None]:
    """Extract and validate budget and quantity. Returns (budget, quantity, early_reply)"""
    if wants_best:
        inherited_budget = inherit_budget(msg_lower, chat_history)
        if inherited_budget is None:
            reply = (
                "Dạ, để tìm bộ PC tốt nhất cho bạn, "
                "em cần biết ngân sách bạn muốn đầu tư là bao nhiêu ạ? "
                "(ví dụ: 30 triệu, 50 triệu...)"
            )
            save_message(user_uid, session_id, user_message, reply)
            return None, quantity, {'chatbot_reply': reply}
        budget = inherited_budget
    else:
        if budget is None:
            budget = inherit_budget(msg_lower, chat_history)

    if budget is not None and budget < 10_000_000:
        if budget <= 0:
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
                    return None, quantity, {'chatbot_reply': reply}
            reply = "Dạ, ngân sách không hợp lệ ạ. Bạn vui lòng nhập lại tầm giá mong muốn nhé!"
        else:
            reply = (
                f"Dạ ngân sách {format_approx_million(budget)} hơi thấp ạ. "
                "Hiện tại các bộ PC bên em đang phân phối có giá từ 10 triệu trở lên. "
                "Bạn cân nhắc nâng thêm chút ngân sách nhé!"
            )
        save_message(user_uid, session_id, user_message, reply)
        return None, quantity, {'chatbot_reply': reply}

    if quantity == 1 and chat_history:
        quantity = inherit_quantity(chat_history)
        
    if quantity > 1 and budget is not None and budget > 0:
        budget_per_unit = budget // quantity
        if budget_per_unit < 10_000_000:
            reply = (
                f"Dạ, với tổng ngân sách {format_approx_million(budget)} cho {quantity} bộ, "
                f"mỗi bộ chỉ có ~{format_approx_million(budget_per_unit)}. "
                "Hiện tại cấu hình PC bên em phân phối có giá thấp nhất từ 10 triệu/bộ ạ. "
                "Bạn có thể tăng ngân sách hoặc giảm số lượng không?"
            )
            save_message(user_uid, session_id, user_message, reply)
            return None, quantity, {'chatbot_reply': reply}
        budget = budget_per_unit

    return budget, quantity, None


def _resolve_filters(search_query: str, user_message: str, chat_history: list) -> tuple[dict, dict, bool, dict, bool]:
    """Returns (brand_filter, component_filter, has_specific_component, upgrade_info, is_upgrade_scenario)"""
    brand_filter = extract_brand_filter(search_query)
    component_filter = extract_component_filter(search_query)

    upgrade_info = extract_upgrade_component(user_message)
    is_upgrade_scenario = upgrade_info.get('is_upgrade', False)

    _apply_upgrade_to_filter(component_filter, upgrade_info)

    if chat_history and not is_reset_intent(user_message):
        print("\n=== 🔍 [DEBUG PC BUILDER] KIỂM TRA LỊCH SỬ ĐỂ KẾ THỪA LINH KIỆN ===")
        inherited = inherit_component_intent(chat_history, max_turns=4)
        
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
    return brand_filter, component_filter, has_specific_component, upgrade_info, is_upgrade_scenario


def _handle_missing_info(budget: int | None, has_final_purpose: bool, has_specific_component: bool, component_filter: dict, combined_message_for_purpose: str, user_uid: str, session_id: str, user_message: str) -> dict | None:
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

    return None


def _build_not_found_reply(component_filter: dict, brand_filter: dict, user_uid: str, session_id: str, user_message: str) -> dict:
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


def _invoke_llm_for_build(system_prompt: str, user_message: str, fallback_reply: str) -> str:
    """Shared LLM invocation for build Q&A."""
    from app.utils.model_utils import get_ollama_model
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{user_message}")
    ])
    llm = ChatOllama(model=get_ollama_model(), temperature=0.1)
    chain = prompt | llm
    
    try:
        res = chain.invoke({"user_message": user_message})
        return res.content.strip()
    except Exception:
        return fallback_reply


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

    # 1. Check for explicit Build ID
    explicit_build_id = extract_explicit_build_id(user_message)
    if explicit_build_id:
        if build_df is not None and not build_df.empty:
            rows = build_df[build_df['BuildID'].str.upper() == explicit_build_id.upper()]
        else:
            rows = None

        if rows is not None and not rows.empty:
            matched_build = rows.iloc[0].to_dict()
            return _answer_about_specific_build(user_uid, session_id, user_message, matched_build)
        
        reply = (
            f"Dạ, em không tìm thấy bộ PC nào có mã **{explicit_build_id}** "
            "trong hệ thống ạ. Bạn kiểm tra lại mã giúp em nhé!"
        )
        save_message(user_uid, session_id, user_message, reply)
        return {'chatbot_reply': reply}

    # 2. Check context overrides
    is_build_pc, is_question_about_current_build, early_reply = _resolve_context_override(
        is_build_pc, user_message, user_message_fixed, msg_lower, chat_history
    )
    if early_reply:
        return early_reply

    if is_question_about_current_build and not is_build_pc:
        return _answer_about_current_build(user_uid, session_id, user_message, chat_history)

    if not is_build_pc:
        return None

    # 3. Handle cheapest-build request
    wants_cheapest = any(kw in msg_lower for kw in CHEAPEST_KEYWORDS)
    wants_best = any(kw in msg_lower for kw in BEST_KEYWORDS)

    if wants_cheapest:
        brand_filter, component_filter, _, upgrade_info, is_upgrade_scenario = _resolve_filters(
            search_query, user_message, chat_history
        )
        
        exclude_builds = get_exclude_builds(chat_history)
        best_build = find_best_build(
            budget=0, user_message=user_message, build_df=build_df,
            exclude_builds=exclude_builds, brand_filter=brand_filter,
            component_filter=component_filter, find_cheapest=True,
        )
        if best_build is None:
            reply = "Dạ, em không tìm được bộ PC nào phù hợp trong kho ạ!"
            save_message(user_uid, session_id, user_message, reply)
            return {'chatbot_reply': reply}
        return _build_reply(user_uid, session_id, user_message, best_build, 0, 'rẻ nhất', 1, is_upgrade_scenario, upgrade_info)

    # 4. Resolve budget and quantity
    budget = extract_budget(user_message)
    quantity = extract_quantity(user_message)
    
    budget, quantity, early_reply = _resolve_budget_and_quantity(
        budget, user_message, msg_lower, quantity, wants_best, chat_history, user_uid, session_id, build_df
    )
    if early_reply:
        return early_reply

    # 5. Extract purpose
    has_final_purpose = any(kw in msg_lower for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list)
    combined_message_for_purpose = user_message
    
    if not has_final_purpose and chat_history:
        for msg in reversed(chat_history):
            if getattr(msg, 'type', '') == 'human':
                if any(kw in msg.content.lower() for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list):
                    combined_message_for_purpose += ' ' + msg.content
                    has_final_purpose = True
                    break

    # 6. Resolve filters
    brand_filter, component_filter, has_specific_component, upgrade_info, is_upgrade_scenario = _resolve_filters(
        search_query, user_message, chat_history
    )

    # 7. Check missing info
    early_reply = _handle_missing_info(
        budget, has_final_purpose, has_specific_component, component_filter, combined_message_for_purpose, user_uid, session_id, user_message
    )
    if early_reply:
        return early_reply

    # 8. Check presets
    preset_reply = get_preset_reply(budget, combined_message_for_purpose, brand_filter, component_filter)
    if preset_reply:
        print(f"⚠️ [PRESET MATCHED] Trả về bộ PC có sẵn cho ngân sách {budget}")
        save_message(user_uid, session_id, user_message, preset_reply)
        return {'chatbot_reply': preset_reply}

    # 9. Find best build
    exclude_builds = get_exclude_builds(chat_history)
    best_build = find_best_build(
        budget=budget, user_message=combined_message_for_purpose, build_df=build_df,
        exclude_builds=exclude_builds, brand_filter=brand_filter, component_filter=component_filter,
    )

    if best_build is None:
        return _build_not_found_reply(component_filter, brand_filter, user_uid, session_id, user_message)

    # 10. Format reply
    purpose_str = infer_purpose(combined_message_for_purpose)
    return _build_reply(user_uid, session_id, user_message, best_build, budget, purpose_str, quantity, is_upgrade_scenario, upgrade_info)


def _build_reply(user_uid: str, session_id: str, user_message: str, best_build: dict,
                 budget: int, purpose_str: str, quantity: int = 1, is_upgrade_scenario: bool = False, upgrade_info: dict = None) -> dict:
    """Build và lưu câu trả lời hoàn chỉnh."""
    reply = format_reply_body(best_build, budget, purpose_str, quantity)
    
    if is_upgrade_scenario and upgrade_info:
        comp_name = upgrade_info.get('cpu_model') or upgrade_info.get('gpu_model') or "linh kiện của bạn"
        reply = f"Em ghi nhận bạn đã có sẵn {comp_name.upper()}. Bộ PC gợi ý dưới đây sẽ tận dụng linh kiện này để build phần còn lại cho bạn:\n\n" + reply
        
    save_message(user_uid, session_id, user_message, reply)
    return {'chatbot_reply': reply}


def _answer_about_current_build(user_uid: str, session_id: str, user_message: str, chat_history: list) -> dict:
    last_build_msg = ""
    for msg in reversed(chat_history):
        if getattr(msg, 'type', '') == 'ai' and BUILD_REPLY_HEADER in msg.content:
            last_build_msg = msg.content
            break
            
    system_prompt = (
        "Bạn là chuyên gia tư vấn linh kiện máy tính tại cửa hàng. Dưới đây là thông số bộ PC mà bạn vừa gợi ý cho khách:\n\n"
        f"{last_build_msg}\n\n"
        "Hãy trả lời câu hỏi của khách hàng về bộ PC này một cách thật ngắn gọn, chính xác, súc tích và thân thiện. Không được tự bịa ra thông số không có trong bộ PC."
    )
    fallback = "Dạ bộ PC này rất ngon trong tầm giá ạ! Bạn có muốn lấy bộ này luôn không?"
    
    reply = _invoke_llm_for_build(system_prompt, user_message, fallback)
    save_message(user_uid, session_id, user_message, reply)
    return {'chatbot_reply': reply}


def _answer_about_specific_build(user_uid: str, session_id: str, user_message: str, build: dict) -> dict:
    build_context = format_build_context(build)

    system_prompt = (
        "Bạn là chuyên gia tư vấn linh kiện máy tính tại cửa hàng. Dưới đây là thông số của bộ PC mà khách đang hỏi tới:\n\n"
        f"{build_context}\n\n"
        "Hãy trả lời câu hỏi của khách hàng về bộ PC này thật ngắn gọn, chính xác, súc tích và thân thiện, dựa hoàn toàn vào thông số trên. Không được tự bịa ra thông số không có trong bộ PC."
    )
    fallback = build_context + "\n\nBạn có muốn em tư vấn thêm về bộ PC này không ạ?"

    reply = _invoke_llm_for_build(system_prompt, user_message, fallback)
    save_message(user_uid, session_id, user_message, reply)
    return {'chatbot_reply': reply}