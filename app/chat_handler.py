"""
Chat endpoint logic — dùng LangChain ChatOllama + ChatPromptTemplate.
"""

from util.response_formatter import word_filter
from app.clarify import chain_invoke, _format_context_directly
from app.clarify import _session_context_cache
from app.core.master_intent import parse_master_intent
from app.core.query_parser import normalize_text
from util.response_formatter import build_range_summary
from memory.memory_store import get_trimmed_history, save_message
from app.search_engine import hybrid_search
from app.clarify import _is_clarification_rejection

# Import các container xử lý context của từng line ý định
from app.compatibility.compatibility import (
    build_compatibility_context, build_suggestion_context
)
from app.price.price_calculator import (
    build_price_calculation_context
)

from app.price.pricing import build_budget_search_context  
from app.specification.specification import build_specification_context 

from app.core.llm_chains import get_basic_search_chain, get_compat_check_chain, get_suggestion_chain
from app.core.query_reformulator import reformulate_query
from app.core.query_parser import normalize_user_message, get_category
from app.specification.context_builder import build_product_context

# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────
def handle_chat(user_message: str, knowledge_base,
                vector_store,
                session_id: str = "default") -> dict:

    if knowledge_base is None:
        return {"chatbot_reply": "HỆ THỐNG CHƯA SẴN SÀNG!"}

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
        if len(q_clean) > 300:
            q_clean = q_clean[:300]

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


        # khoi tao 
        context = ""
        format_hint = ""
        matched_items = []
        chain = None
        
        
        # 4.  ĐIỀU HƯỚNG context
        # 🔹 NHÁNH 1: KIỂM TRA TƯƠNG THÍCH (compatibility check )
        if parsed_intent.intent == "compatibility":
            context = build_compatibility_context(parsed_intent, knowledge_base, vector_store)
            chain = get_compat_check_chain()

        # 🔹 NHÁNH 2: de xuat linh kien phu hop
        elif parsed_intent.intent == "suggestion":
            context = build_suggestion_context(parsed_intent, knowledge_base, vector_store)
            chain = get_suggestion_chain() 
            
        # 🔹 NHÁNH 3: TÍNH TỔNG TIỀN
        elif parsed_intent.intent == "price_calculation":
            context = build_price_calculation_context(parsed_intent, knowledge_base, vector_store)
            chain = get_basic_search_chain() # Hoặc một chain chuyên tính toán

        # 🔹 NHÁNH 4: HỎI THÔNG SỐ CỤ THỂ (Mới)
        elif parsed_intent.intent == "specification":
            context, format_hint = build_specification_context(
                parsed_intent, category, knowledge_base, vector_store, search_query
            )
            chain = get_basic_search_chain()

        # Nhánh 5: Tìm kiếm cấu hình theo ví tiền/ngân sách 
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
                    # Nếu chưa cấu hình chain chuyên dụng, dùng xích tìm kiếm cơ bản để hồi đáp
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