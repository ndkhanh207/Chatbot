from app.core.query_parser import detect_brand
from app.specification.context_builder import build_product_context
from app.price.price_logic import filter_knowledge_base_by_price
from app.utils.response_formatter import build_range_summary



def build_budget_search_context(parsed_intent, msg_lower, category, knowledge_base, user_message, search_query) -> tuple[str, str]:
    """
    Container xử lý riêng cho luồng tìm kiếm linh kiện theo tầm giá / ngân sách tối đa.
    Trả về: (context, format_hint)
    """
    brand = detect_brand(msg_lower)
    
    # Lọc trực tiếp từ DB/DataFrame các món có giá từ 0đ -> mức ngân sách tối đa
    matched_items, total_count = filter_knowledge_base_by_price(
        knowledge_base, 
        category, 
        0.0, 
        float(parsed_intent.budget_amount), 
        brand=brand, 
        top_k=5
    )
    
    context = build_product_context(search_query, category, matched_items)
    
    format_hint = ""
    if matched_items:
        format_hint = build_range_summary(user_message, matched_items)
        format_hint += f"\nLưu ý: Đã lọc linh kiện có giá dưới {parsed_intent.budget_amount:,} VNĐ."
        
        if total_count and total_count > len(matched_items):
            format_hint += f"\n(Lưu ý: còn {total_count - len(matched_items)} sản phẩm khác cũng nằm trong khoảng giá này, không hiển thị hết ở đây.)"
            
    return context, format_hint