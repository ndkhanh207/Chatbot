"""
Chat endpoint logic — dùng LangChain ChatOllama + ChatPromptTemplate.
"""

import re
import json
from app.utils.response_formatter import word_filter, build_range_summary
from app.clarify import chain_invoke, chain_stream, _format_context_directly, _session_context_cache, _is_clarification_rejection
from app.core.master_intent import parse_master_intent
from app.core.query_parser import normalize_text, normalize_user_message, get_category
from app.memory.memory_store import get_trimmed_history, save_message
from app.core.search_engine import hybrid_search

# Import các container xử lý context của từng line ý định
from app.compatibility.compatibility import build_compatibility_context, build_suggestion_context
from app.price.price_calculator import build_price_calculation_context
from app.price.pricing import build_budget_search_context, build_price_check_context  
from app.specification.specification import build_specification_context 

from app.core.llm_chains import get_basic_search_chain, get_compat_check_chain, get_suggestion_chain
from app.core.query_reformulator import reformulate_query
from app.specification.context_builder import build_product_context
from app.pc_builder.advisor import detect_build_pc_intent
from app.pc_builder.flow import handle_pc_build_flow

# ──────────────────────────────────────────────
# Prompt Injection Guard & Security
# ──────────────────────────────────────────────
from app.core.injection_guard import sanitize_input

MAX_INPUT_LENGTH = 500  # Ký tự tối đa

# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────
def handle_chat(user_message: str, knowledge_base,
                vector_store,
                session_id: str = "default",
                build_df=None) -> dict:

    if knowledge_base is None:
        return {"chatbot_reply": "HỆ THỐNG CHƯA SẴN SÀNG!"}

    # ── Security: Kiểm tra độ dài và Prompt Injection ──
    if len(user_message) > MAX_INPUT_LENGTH:
        return {"chatbot_reply": "Câu hỏi quá dài rồi ạ! Bạn vui lòng rút gọn trong 500 ký tự giúp em nhé 😊"}

    _, is_injection = sanitize_input(user_message)
    if is_injection:
        return {"chatbot_reply": "Dạ em chỉ hỗ trợ tư vấn linh kiện và bộ máy tính thôi ạ! Bạn có câu hỏi nào về PC không? 😊"}

    msg_clean = user_message.strip().lower()

    # ── FEATURE: Giao tiếp cơ bản (Không gọi DB / LLM) ──
    CASUAL_GREETINGS = ['xin chào', 'chào bạn', 'hi', 'hello', 'chào em', 'chào bot']
    CASUAL_THANKS = ['cảm ơn', 'thank', 'tks', 'ok', 'oke', 'okela', 'dạ', 'vâng', 'tuyệt vời', 'đã hiểu', 'hay quá']
    CASUAL_BYE = ['tạm biệt', 'bye', 'hẹn gặp lại']

    if len(msg_clean) < 30:
        if any(msg_clean == g or msg_clean.startswith(g + ' ') for g in CASUAL_GREETINGS):
            return {"chatbot_reply": "Dạ em chào bạn! Em là trợ lý tư vấn máy tính, em có thể giúp gì cho bạn hôm nay ạ? 😊"}
        if any(msg_clean == t or msg_clean.startswith(t + ' ') for t in CASUAL_THANKS):
            return {"chatbot_reply": "Dạ vâng ạ! Nếu bạn cần tư vấn cấu hình hay linh kiện gì thêm cứ nhắn em nhé. 😊"}
        if any(msg_clean == b or msg_clean.startswith(b + ' ') for b in CASUAL_BYE):
            return {"chatbot_reply": "Dạ tạm biệt bạn! Chúc bạn một ngày tốt lành ạ! 😊"}

    # ── FEATURE: Off-topic guard rail ──
    # Chặn các câu hỏi hoàn toàn ngoài lĩnh vực PC
    OFF_TOPIC_TRIGGERS = [
        'laptop', 'macbook', 'điện thoại', 'smartphone', 'iphone', 'samsung',
        'tivi', 'máy lạnh', 'điều hòa', 'tủ lạnh', 'máy giặt',
        'xe máy', 'ô tô', 'xe hơi', 'xe đạp',
        'thời tiết', 'nấu ăn', 'công thức', 'quần áo', 'thời trang', 'giày',
        'chứng khoán', 'bitcoin', 'crypto', 'cổ phiếu',
        'bóng đá', 'thể thao', 'ca sĩ', 'diễn viên', 'phim', 'nhạc',
        'làm thơ', 'kể chuyện', 'viết code', 'viết bài', 'giải toán'
    ]
    msg_lower_check = user_message.lower()
    # Chỉ từ chối nếu off-topic VÀ không liên quan gì đến PC/linh kiện
    PC_SAFE_TERMS = ['pc', 'cpu', 'gpu', 'ram', 'ssd', 'vga', 'card', 'mainboard', 'build', 'máy tính']
    is_off_topic = any(t in msg_lower_check for t in OFF_TOPIC_TRIGGERS)
    is_pc_related = any(t in msg_lower_check for t in PC_SAFE_TERMS)
    if is_off_topic and not is_pc_related:
        return {"chatbot_reply": "Dạ em chỉ chuyên tư vấn linh kiện và cấu hình máy tính để bàn thôi ạ! Bạn có cần tư vấn CPU, GPU, hay build bộ PC không? 😊"}

    try:
        # 1. Normalise & detect intent
        user_message_fixed = normalize_user_message(user_message)
        msg_lower          = normalize_text(user_message_fixed)
        category = get_category(msg_lower)

        # 2. Lấy lịch sử TRƯỚC khi search (để reformulate)
        chat_history = get_trimmed_history(session_id)

        # 3. Reformulate query mơ hồ → rõ ràng trước khi search
        search_query = reformulate_query(user_message_fixed, chat_history)
        q_clean = search_query.replace("\n", " ").strip()

        if _is_clarification_rejection(user_message_fixed):
            cached = _session_context_cache.get(session_id)
            if cached:
                print(f"♻️ [REJECTION-FALLBACK] Dùng lại context từ intent: {cached['intent']}")
                response = cached["chain"].invoke({
                    "context":      cached["context"],
                    "format_hint":  cached.get("format_hint", ""),
                    "user_message": user_message_fixed,
                    "chat_history": chat_history,
                })
                reply = response.content
                clean_reply = word_filter(reply)
                save_message(session_id, user_message_fixed, clean_reply)
                return {"chatbot_reply": clean_reply}

        # 3.5. Bóc tách ý định bằng LLM sớm để lấy chính xác loại linh kiện khách cần tìm
        parsed_intent = parse_master_intent(search_query)
        if parsed_intent.category != "none":
            category = parsed_intent.category.upper()

        # Fallback: detect category từ target_product khi LLM trả "none"
        if (not category or category == "NONE") and parsed_intent.target_product != "none":
            tp = parsed_intent.target_product.lower()
            if any(k in tp for k in ['i3', 'i5', 'i7', 'i9', 'ryzen', 'core']):
                category = 'CPU'
            elif any(k in tp for k in ['rtx', 'gtx', 'rx', 'radeon', 'geforce']):
                category = 'GPU'

        # ── XỬ LÝ NHÁNH BUILD PC TRỌN BỘ ──
        is_build_pc = (parsed_intent.intent == "build_pc") or detect_build_pc_intent(user_message_fixed)
        pc_build_result = handle_pc_build_flow(
            session_id=session_id,
            user_message=user_message,
            user_message_fixed=user_message_fixed,
            msg_lower=msg_lower,
            chat_history=chat_history,
            build_df=build_df,
            is_build_pc=is_build_pc
        )
        if pc_build_result is not None:
            return pc_build_result

        # khoi tao 
        context = ""
        format_hint = ""
        matched_items = []
        chain = None
        
        # 4. ĐIỀU HƯỚNG context
        # 🔹 NHÁNH 1: KIỂM TRA TƯƠNG THÍCH (compatibility check)
        if parsed_intent.intent == "compatibility":
            context = build_compatibility_context(parsed_intent, knowledge_base, vector_store)
            chain = get_compat_check_chain()

        # 🔹 NHÁNH 2: de xuat linh kien phu hop
        # 🔹 NHÁNH 2: de xuat linh kien phu hop
        elif parsed_intent.intent == "suggestion":
            context = build_suggestion_context(parsed_intent, knowledge_base, vector_store)
            chain = get_suggestion_chain() 
            
        # 🔹 NHÁNH 3: TÍNH TỔNG TIỀN
        elif parsed_intent.intent == "price_calculation":
            context = build_price_calculation_context(parsed_intent, knowledge_base, vector_store)
            chain = get_basic_search_chain() # Hoặc một chain chuyên tính toán

        # 🔹 NHÁNH 4: HỎI THÔNG SỐ CỤ THỂ
        elif parsed_intent.intent == "specification":
            context, format_hint = build_specification_context(
                parsed_intent, category, knowledge_base, vector_store, search_query
            )
            chain = get_basic_search_chain()

        # 🔹 NHÁNH 4b: HỎI GIÁ CỦA 1 MÓN CỤ THỂ (price check)
        elif parsed_intent.intent == "price_check":
            context, format_hint = build_price_check_context(
                parsed_intent, category, knowledge_base, vector_store, search_query
            )
            chain = get_basic_search_chain()

        # Nhánh 5: Tìm kiếm cấu hình theo ví tiền/ngân sách (cho 1 linh kiện đơn lẻ)
        elif parsed_intent.intent == "budget_search":
            context, format_hint = build_budget_search_context(
                parsed_intent, msg_lower, category, knowledge_base, user_message, search_query
            )
            chain = get_suggestion_chain()

        # 🔹 NHÁNH 6: TÌM KIẾM/HỎI GIÁ CHUNG CHUNG (Fallback)
        else:
            matched_items = hybrid_search(q_clean, category, 4, knowledge_base, vector_store) or []
            context = build_product_context(search_query, category, matched_items, include_all_fields=True)
            chain = get_basic_search_chain()
        
        if not context or parsed_intent.intent == "none":
            if parsed_intent.intent != "budget_search": # Giữ nguyên cơ chế thông báo trống của budget
                print(f"⚠️ [ROUTER-FALLBACK] Kích hoạt lưới cứu vớt diện rộng cho intent: {parsed_intent.intent.upper()}")
                matched_items = hybrid_search(q_clean, category, 4, knowledge_base, vector_store) or []
                if matched_items:
                    context = build_product_context(search_query, category, matched_items)
                    if not chain:
                        chain = get_basic_search_chain()
                        
        if not context:
            if parsed_intent.intent == "budget_search":
                return {"chatbot_reply": "Dạ hiện tại cửa hàng chưa có sản phẩm nào trong khoảng giá này ạ."}
            return {
                "chatbot_reply": "Dạ hiện tại em chưa tìm thấy mã sản phẩm này trong kho ạ."
            }

        # 7. Lưu context vào cache để dùng khi user từ chối khi bot hỏi lại thông tin
        if context and len(context) > 50 and chain is not None:
            _session_context_cache[session_id] = {
                "context":     context,
                "format_hint": format_hint,
                "chain":       chain,
                "intent":      parsed_intent.intent,
            }
        # 6. Debug Log ra màn hình console để theo dõi luồng đi
        print("\n" + "═"*60)
        print(f"🔍 Cau hoi goc: {user_message}")
        print(f"🔹 2. Từ khóa dùng để Search (q_clean): '{q_clean}'")
        print(f"🔍 [HỆ THỐNG DEBUG MASTER ROUTER] - Session: {session_id}")
        print(f"🔹 Ý định nhận diện: {parsed_intent.intent.upper()}")
        print(f"🔹 Tên linh kiện đích: {parsed_intent.target_product}")
        print(f"🔹 Phân loại danh mục: {category}")
        print(f"🔹 Nội dung [format_hint] nạp vào:\n{repr(format_hint)}")
        print(f"🔹 5. Nội dung [context] của Bot:\n{context}")
        print("═"*60 + "\n")

        # Gọi AI xử lý với đúng Trạm đã chọn có áp dụng retry 
        response = chain_invoke(chain, context, format_hint, user_message_fixed, chat_history, parsed_intent)

        # nếu bot hỏi vặn lại khách lần 1 thì retry với template emergency
        # nếu bot hỏi vặn lại khách lần 2 thì bypass LLM hoàn toàn
        
        if response is None:
            response = _format_context_directly(context, parsed_intent.intent)

        clean_reply = word_filter(response)
        save_message(session_id, user_message_fixed, clean_reply)

        print(f"[HISTORY SAVED] AI reply lưu vào DB ({len(clean_reply)} ký tự gốc)")
        return {"chatbot_reply": clean_reply}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"chatbot_reply": f"❌ Lỗi hệ thống: {str(e)}"}


def handle_chat_stream(user_message: str, knowledge_base,
                       vector_store,
                       session_id: str = "default",
                       build_df=None,
                       stop_event=None):
    if knowledge_base is None:
        yield f"data: {json.dumps({'chunk': 'HỆ THỐNG CHƯA SẴN SÀNG!'}, ensure_ascii=False)}\n\n"
        return

    # ── Security: Kiểm tra độ dài và Prompt Injection ──
    if len(user_message) > MAX_INPUT_LENGTH:
        yield f"data: {json.dumps({'chunk': 'Câu hỏi quá dài rồi ạ! Bạn vui lòng rút gọn trong 500 ký tự giúp em nhé 😊'}, ensure_ascii=False)}\n\n"
        return

    _, is_injection = sanitize_input(user_message)
    if is_injection:
        yield f"data: {json.dumps({'chunk': 'Dạ em chỉ hỗ trợ tư vấn linh kiện và bộ máy tính thôi ạ! Bạn có câu hỏi nào về PC không? 😊'}, ensure_ascii=False)}\n\n"
        return

    msg_clean = user_message.strip().lower()

    # ── FEATURE: Giao tiếp cơ bản (Không gọi DB / LLM) ──
    CASUAL_GREETINGS = ['xin chào', 'chào bạn', 'hi', 'hello', 'chào em', 'chào bot']
    CASUAL_THANKS = ['cảm ơn', 'thank', 'tks', 'ok', 'oke', 'okela', 'dạ', 'vâng', 'tuyệt vời', 'đã hiểu', 'hay quá']
    CASUAL_BYE = ['tạm biệt', 'bye', 'hẹn gặp lại']

    if len(msg_clean) < 30:
        if any(msg_clean == g or msg_clean.startswith(g + ' ') for g in CASUAL_GREETINGS):
            yield f"data: {json.dumps({'chunk': 'Dạ em chào bạn! Em là trợ lý tư vấn máy tính, em có thể giúp gì cho bạn hôm nay ạ? 😊'}, ensure_ascii=False)}\n\n"
            return
        if any(msg_clean == t or msg_clean.startswith(t + ' ') for t in CASUAL_THANKS):
            yield f"data: {json.dumps({'chunk': 'Dạ vâng ạ! Nếu bạn cần tư vấn cấu hình hay linh kiện gì thêm cứ nhắn em nhé. 😊'}, ensure_ascii=False)}\n\n"
            return
        if any(msg_clean == b or msg_clean.startswith(b + ' ') for b in CASUAL_BYE):
            yield f"data: {json.dumps({'chunk': 'Dạ tạm biệt bạn! Chúc bạn một ngày tốt lành ạ! 😊'}, ensure_ascii=False)}\n\n"
            return

    # ── FEATURE: Off-topic guard rail ──
    OFF_TOPIC_TRIGGERS = [
        'laptop', 'macbook', 'điện thoại', 'smartphone', 'iphone', 'samsung',
        'tivi', 'máy lạnh', 'điều hòa', 'tủ lạnh', 'máy giặt',
        'xe máy', 'ô tô', 'xe hơi', 'xe đạp',
        'thời tiết', 'nấu ăn', 'công thức', 'quần áo', 'thời trang', 'giày',
        'chứng khoán', 'bitcoin', 'crypto', 'cổ phiếu',
        'bóng đá', 'thể thao', 'ca sĩ', 'diễn viên', 'phim', 'nhạc',
        'làm thơ', 'kể chuyện', 'viết code', 'viết bài', 'giải toán'
    ]
    msg_lower_check = user_message.lower()
    PC_SAFE_TERMS = ['pc', 'cpu', 'gpu', 'ram', 'ssd', 'vga', 'card', 'mainboard', 'build', 'máy tính']
    is_off_topic = any(t in msg_lower_check for t in OFF_TOPIC_TRIGGERS)
    is_pc_related = any(t in msg_lower_check for t in PC_SAFE_TERMS)
    if is_off_topic and not is_pc_related:
        yield f"data: {json.dumps({'chunk': 'Dạ em chỉ chuyên tư vấn linh kiện và cấu hình máy tính để bàn thôi ạ! Bạn có cần tư vấn CPU, GPU, hay build bộ PC không? 😊'}, ensure_ascii=False)}\n\n"
        return

    try:
        # ── TTFB TỨC THÌ (0.01s): Gửi ngay tín hiệu đang xử lý ──
        yield f"data: {json.dumps({'chunk': '🔄 Đang phân tích câu hỏi...\n'}, ensure_ascii=False)}\n\n"

        user_message_fixed = normalize_user_message(user_message)
        msg_lower          = normalize_text(user_message_fixed)
        category = get_category(msg_lower)

        chat_history = get_trimmed_history(session_id)
        search_query = reformulate_query(user_message_fixed, chat_history)
        q_clean = search_query.replace("\n", " ").strip()

        if _is_clarification_rejection(user_message_fixed):
            cached = _session_context_cache.get(session_id)
            if cached:
                print(f"♻️ [REJECTION-FALLBACK-STREAM] Dùng lại context từ intent: {cached['intent']}")
                full_text = ""
                for chunk in cached["chain"].stream({
                    "context":      cached["context"],
                    "format_hint":  cached.get("format_hint", ""),
                    "user_message": user_message_fixed,
                    "chat_history": chat_history,
                }):
                    if stop_event and stop_event.is_set():
                        break
                    content = chunk.content if hasattr(chunk, "content") else str(chunk)
                    full_text += content
                    yield f"data: {json.dumps({'chunk': content}, ensure_ascii=False)}\n\n"
                clean_reply = word_filter(full_text)
                save_message(session_id, user_message_fixed, clean_reply)
                return

        parsed_intent = parse_master_intent(search_query)
        yield f"data: {json.dumps({'chunk': f'🔍 Đang tìm kiếm trong kho dữ liệu ({parsed_intent.intent.upper()})...\n\n'}, ensure_ascii=False)}\n\n"

        if parsed_intent.category != "none":
            category = parsed_intent.category.upper()

        if (not category or category == "NONE") and parsed_intent.target_product != "none":
            tp = parsed_intent.target_product.lower()
            if any(k in tp for k in ['i3', 'i5', 'i7', 'i9', 'ryzen', 'core']):
                category = 'CPU'
            elif any(k in tp for k in ['rtx', 'gtx', 'rx', 'radeon', 'geforce']):
                category = 'GPU'

        # ── XỬ LÝ NHÁNH BUILD PC TRỌN BỘ ──
        is_build_pc = (parsed_intent.intent == "build_pc") or detect_build_pc_intent(user_message_fixed)
        pc_build_result = handle_pc_build_flow(
            session_id=session_id,
            user_message=user_message,
            user_message_fixed=user_message_fixed,
            msg_lower=msg_lower,
            chat_history=chat_history,
            build_df=build_df,
            is_build_pc=is_build_pc
        )
        if pc_build_result is not None:
            yield f"data: {json.dumps({'chunk': pc_build_result.get('chatbot_reply', '')}, ensure_ascii=False)}\n\n"
            return

        context = ""
        format_hint = ""
        matched_items = []
        chain = None
        
        if parsed_intent.intent == "compatibility":
            context = build_compatibility_context(parsed_intent, knowledge_base, vector_store)
            chain = get_compat_check_chain()
        elif parsed_intent.intent == "suggestion":
            context = build_suggestion_context(parsed_intent, knowledge_base, vector_store)
            chain = get_suggestion_chain() 
        elif parsed_intent.intent == "price_calculation":
            context = build_price_calculation_context(parsed_intent, knowledge_base, vector_store)
            chain = get_basic_search_chain()
        elif parsed_intent.intent == "specification":
            context, format_hint = build_specification_context(
                parsed_intent, category, knowledge_base, vector_store, search_query
            )
            chain = get_basic_search_chain()
        elif parsed_intent.intent == "price_check":
            context, format_hint = build_price_check_context(
                parsed_intent, category, knowledge_base, vector_store, search_query
            )
            chain = get_basic_search_chain()
        elif parsed_intent.intent == "budget_search":
            context, format_hint = build_budget_search_context(
                parsed_intent, msg_lower, category, knowledge_base, user_message, search_query
            )
            chain = get_suggestion_chain()
        else:
            matched_items = hybrid_search(q_clean, category, 4, knowledge_base, vector_store) or []
            context = build_product_context(search_query, category, matched_items, include_all_fields=True)
            chain = get_basic_search_chain()
        
        if not context or parsed_intent.intent == "none":
            if parsed_intent.intent != "budget_search":
                print(f"⚠️ [ROUTER-FALLBACK-STREAM] Kích hoạt lưới cứu vớt diện rộng cho intent: {parsed_intent.intent.upper()}")
                matched_items = hybrid_search(q_clean, category, 4, knowledge_base, vector_store) or []
                if matched_items:
                    context = build_product_context(search_query, category, matched_items)
                    if not chain:
                        chain = get_basic_search_chain()
                        
        if not context:
            if parsed_intent.intent == "budget_search":
                yield f"data: {json.dumps({'chunk': 'Dạ hiện tại cửa hàng chưa có sản phẩm nào trong khoảng giá này ạ.'}, ensure_ascii=False)}\n\n"
                return
            yield f"data: {json.dumps({'chunk': 'Dạ hiện tại em chưa tìm thấy mã sản phẩm này trong kho ạ.'}, ensure_ascii=False)}\n\n"
            return

        if context and len(context) > 50 and chain is not None:
            _session_context_cache[session_id] = {
                "context":     context,
                "format_hint": format_hint,
                "chain":       chain,
                "intent":      parsed_intent.intent,
            }

        print("\n" + "═"*60)
        print(f"🔍 Cau hoi goc (Stream): {user_message}")
        print(f"🔹 2. Từ khóa dùng để Search (q_clean): '{q_clean}'")
        print(f"🔍 [HỆ THỐNG DEBUG MASTER ROUTER STREAM] - Session: {session_id}")
        print(f"🔹 Ý định nhận diện: {parsed_intent.intent.upper()}")
        print(f"🔹 Tên linh kiện đích: {parsed_intent.target_product}")
        print(f"🔹 Phân loại danh mục: {category}")
        print(f"🔹 Nội dung [format_hint] nạp vào:\n{repr(format_hint)}")
        print(f"🔹 5. Nội dung [context] của Bot:\n{context}")
        print("═"*60 + "\n")

        full_reply = ""
        for chunk_text in chain_stream(chain, context, format_hint, user_message_fixed, chat_history, parsed_intent, stop_event):
            full_reply += chunk_text
            yield f"data: {json.dumps({'chunk': chunk_text}, ensure_ascii=False)}\n\n"

        clean_reply = word_filter(full_reply)
        save_message(session_id, user_message_fixed, clean_reply)
        print(f"[HISTORY SAVED STREAM] AI reply lưu vào DB ({len(clean_reply)} ký tự gốc)")

    except Exception as e:
        import traceback
        traceback.print_exc()
        yield f"data: {json.dumps({'chunk': f'❌ Lỗi hệ thống: {str(e)}'}, ensure_ascii=False)}\n\n"