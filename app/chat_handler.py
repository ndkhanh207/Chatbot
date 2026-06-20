"""
Chat endpoint logic — dùng LangChain ChatOllama + ChatPromptTemplate.
"""

from app.core.query_parser import normalize_text
from util.response_formatter import build_range_summary, parse_price_range_vnd, world_filter
from memory.memory_store import get_trimmed_history, save_message
from app.search_engine import hybrid_search

from app.compact.compatibility import (
    build_compatibility_context, build_suggestion_context, parse_compat_intent
)
from app.price.price_calculator import (
    build_price_calculation_context, is_price_calculation_query,
)

from app.core.llm_chains import get_chain, get_compat_check_chain, get_suggestion_chain
from app.core.query_reformulator import reformulate_query
from app.core.query_parser import normalize_user_message, detect_intent, get_category, detect_brand
from app.core.context_builder import build_product_context, filter_knowledge_base_by_price

# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────
def handle_chat(user_message: str, knowledge_base,
                vector_store,
                session_id: str = "default") -> dict:

    if knowledge_base is None:
        return {"chatbot_reply": "HỆ THỐNG CHƯA SẴN SÀNG!"}

    # 1. Normalise & detect intent
    user_message_fixed = normalize_user_message(user_message)
    msg_lower          = normalize_text(user_message_fixed)
    is_compat, has_cpu, has_gpu, has_main = detect_intent(msg_lower)
    is_price_calc = is_price_calculation_query(msg_lower)
    category = get_category(msg_lower)

    # 2. Lấy lịch sử TRƯỚC khi search (để reformulate)
    chat_history = get_trimmed_history(session_id)

    # 3. Reformulate query mơ hồ → rõ ràng trước khi search
    search_query = reformulate_query(user_message_fixed, chat_history)
    q_clean = search_query.replace("\n", " ").strip()
    if len(q_clean) > 300:
        q_clean = q_clean[:100]

    # 3.5. Bóc tách ý định bằng LLM sớm để lấy chính xác loại linh kiện khách cần tìm
    intent = parse_compat_intent(search_query)
    if intent.looking_for != "none":
        category = intent.looking_for.upper()

    # 4. Fetch matched_items
    price_range = parse_price_range_vnd(user_message_fixed)
    brand = detect_brand(msg_lower)
    total_count = None

    if price_range or (brand and category == "GPU"):
        lo, hi = price_range if price_range else (0.0, float("inf"))
        matched_items, total_count = filter_knowledge_base_by_price(
            knowledge_base, category, lo, hi, brand=brand, top_k=10
        )
    else:
        matched_items = hybrid_search(q_clean, category, 4, knowledge_base, vector_store) or []

    if price_range and not matched_items:
        return {
            "chatbot_reply": (
                "Dạ hiện tại cửa hàng chưa có sản phẩm nào trong khoảng giá này ạ. "
                "Bạn có muốn em gợi ý mức giá gần nhất không?"
            )
        }

    # 5. Build compat context
    compatibility_context = ""
    if intent.intent == "compatibility":
        compatibility_context = build_compatibility_context(
            intent, knowledge_base, vector_store
        )
    elif intent.intent == "suggestion":
        compatibility_context = build_suggestion_context(
            intent, knowledge_base, vector_store
        )
    elif intent.intent == "price_calculation" or is_price_calc:
        compatibility_context = build_price_calculation_context(
            intent, knowledge_base, vector_store
        )

    # 6. Build product context
    product_context = ""
    if not compatibility_context:
        product_context = build_product_context(
            search_query, category, matched_items
        )

    # 7. Nothing found?
    if not compatibility_context and not product_context:
        return {
            "chatbot_reply": (
                "Dạ hiện tại em chưa tìm thấy mã sản phẩm này trong kho. "
                "Bạn cung cấp rõ tên model giúp em nhé!"
            )
        }

    # 8. Build context & format_hint
    context     = compatibility_context if compatibility_context else product_context
    format_hint = build_range_summary(user_message, matched_items) \
                  if not compatibility_context else ""

    if price_range and total_count and total_count > len(matched_items):
        format_hint += (
            f"\n(Lưu ý: còn {total_count - len(matched_items)} sản phẩm khác "
            f"cũng nằm trong khoảng giá này, không hiển thị hết ở đây.)"
        )

    # 9. Invoke chain với memory
    try:
        print("\n" + "═"*60)
        print(f"🔍 [HỆ THỐNG DEBUG CHAT] - Session ID: {session_id}")
        print(f"🔹 1. Câu hỏi gốc của khách: '{user_message}'")
        print(f"🔹 2. Từ khóa dùng để Search (q_clean): '{q_clean}'")
        print(f"🔹 3. Số lượng linh kiện tìm thấy trong DB: {len(matched_items)} món"
              + (f" (tổng khớp điều kiện giá: {total_count})" if total_count else ""))
        print(f"🔹 4. Nội dung [format_hint] sinh ra:\n{repr(format_hint)}")
        print(f"🔹 5. Nội dung [context] nhét vào miệng Bot:\n{context}")
        print("═"*60 + "\n")

        # Bẻ lái luồng chạy tại đây! Giao việc chuẩn cho từng Trạm
        if intent.intent == "compatibility":
            chain = get_compat_check_chain()
        elif intent.intent == "suggestion":
            chain = get_suggestion_chain()
        else:
            chain = get_chain() # Rơi vào đây khi intent là "none" (hỏi giá, specs, tìm SP...)
       
        # Gọi AI xử lý với đúng Trạm đã chọn
        response = chain.invoke({
            "context":      context,
            "format_hint":  format_hint,
            "user_message": user_message_fixed,
            "chat_history": chat_history,
        })

        reply = response.content
        clean_reply = world_filter(reply)
        save_message(session_id, user_message_fixed, clean_reply)
        return {"chatbot_reply": clean_reply}

    except Exception as e:
        return {"chatbot_reply": f"❌ Lỗi bộ não AI: {str(e)}"}