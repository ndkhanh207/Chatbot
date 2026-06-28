import re
from app.core.query_parser import detect_brand
from app.specification.context_builder import build_product_context
from app.price.price_logic import filter_knowledge_base_by_price
from app.utils.response_formatter import build_range_summary
from app.core.search_engine import hybrid_search
from app.compatibility.compat_logic import _get_field
from app.price.pricing_util import format_currency_vietnam


def build_price_check_context(parsed_intent, category, knowledge_base, vector_store, search_query) -> tuple[str, str]:
    """
    Container xử lý riêng cho luồng kiểm tra giá bán của 1 linh kiện cụ thể (price check).
    Trả về: (context, format_hint)
    """
    query = parsed_intent.target_product if parsed_intent.target_product != "none" else search_query
    matched_items = hybrid_search(query, category, 3, knowledge_base, vector_store) or []
    
    context = build_product_context(search_query, category, matched_items, include_all_fields=True)
    
    format_hint = ""
    if matched_items:
        item = matched_items[0]
        price_raw = _get_field(item, "giá", "price", default=0)
        name_disp = _get_field(item, "tên", "name", default=query)
        price_str = format_currency_vietnam(price_raw)
        format_hint = (
            f"\nThông tin giá chính xác từ kho cho '{name_disp}': {price_str} VNĐ.\n"
            f"Lưu ý quan trọng: Hãy báo chính xác mức giá {price_str} VNĐ này cho khách hàng."
        )
        
    return context, format_hint


def build_budget_search_context(parsed_intent, msg_lower, category, knowledge_base, user_message, search_query) -> tuple[str, str]:
    """
    Container xử lý riêng cho luồng tìm kiếm linh kiện theo tầm giá / ngân sách tối đa,
    kèm phân tích Regex động cho khoảng giá (từ X đến Y), top rẻ nhất (asc), đắt nhất (desc).
    Trả về: (context, format_hint)
    """
    brand = detect_brand(msg_lower)
    
    lo = 0.0
    hi = float(parsed_intent.budget_amount) if getattr(parsed_intent, 'budget_amount', 0) > 0 else 999999999.0
    top_k = 5
    sort_order = "none"
    
    # Phân tích Regex trực tiếp từ msg_lower
    # 1. Tìm cụm 'từ X (triệu|tr) đến Y (triệu|tr)'
    m_range = re.search(r'\btừ\s+(\d+(?:\.\d+)?)\s*(?:triệu|tr)?\s*(?:đến|tới|-)\s*(\d+(?:\.\d+)?)\s*(?:triệu|tr)\b', msg_lower)
    if m_range:
        lo = float(m_range.group(1)) * 1000000
        hi = float(m_range.group(2)) * 1000000
        
    # 2. Tìm yêu cầu sắp xếp rẻ nhất / đắt nhất
    if any(k in msg_lower for k in ["rẻ nhất", "thấp nhất", "giá rẻ", "giá thấp"]):
        sort_order = "asc"
    elif any(k in msg_lower for k in ["đắt nhất", "cao nhất", "giá cao", "max giá"]):
        sort_order = "desc"
        
    # 3. Tìm số lượng top K
    m_top = re.search(r'\b(top|cho xem|list|liệt kê)\s+(\d+)\b', msg_lower)
    if m_top:
        top_k = int(m_top.group(2))
    
    # Lọc trực tiếp từ DB/DataFrame
    matched_items, total_count = filter_knowledge_base_by_price(
        knowledge_base, 
        category, 
        lo, 
        hi, 
        brand=brand, 
        top_k=top_k,
        sort_order=sort_order
    )
    
    context = build_product_context(search_query, category, matched_items)
    
    format_hint = ""
    if matched_items:
        format_hint = build_range_summary(user_message, matched_items)
        if lo > 0 and hi < 999999999.0:
            format_hint += f"\nLưu ý: Đã lọc linh kiện có giá từ {int(lo):,} VNĐ đến {int(hi):,} VNĐ."
        elif hi < 999999999.0:
            format_hint += f"\nLưu ý: Đã lọc linh kiện có giá dưới {int(hi):,} VNĐ."
        elif lo > 0:
            format_hint += f"\nLưu ý: Đã lọc linh kiện có giá trên {int(lo):,} VNĐ."
            
        if sort_order == "asc":
            format_hint += f"\nDanh sách dưới đây là các sản phẩm CÓ GIÁ RẺ NHẤT / THẤP NHẤT trong tầm giá. Hãy liệt kê rõ danh sách này cho khách hàng."
        elif sort_order == "desc":
            format_hint += f"\nDanh sách dưới đây là các sản phẩm CÓ GIÁ ĐẮT NHẤT / CAO NHẤT trong tầm giá. Hãy liệt kê rõ danh sách này cho khách hàng."
            
        if total_count and total_count > len(matched_items):
            format_hint += f"\n(Lưu ý: còn {total_count - len(matched_items)} sản phẩm khác cũng nằm trong khoảng giá này, không hiển thị hết ở đây.)"
            
    return context, format_hint