import re
from app.core.query_parser import detect_brand
from app.guard.response_formatter import build_range_summary
from app.catalog.context_builder import build_product_context
from app.catalog import ProductQuery, ShopCatalog
from app.catalog.lookup import lookup_and_rerank
from app.utils.format import get_field, format_currency_vietnam


def build_price_check_context(parsed_entities, category, catalog: ShopCatalog, search_query) -> tuple[str, str]:
    """
    Container xử lý riêng cho luồng kiểm tra giá bán của 1 linh kiện cụ thể (price check).
    Trả về: (context, format_hint)
    """
    lookup_term = parsed_entities.target_product
    if not lookup_term or lookup_term.strip().lower() == "none":
        for fallback in [parsed_entities.cpu, parsed_entities.gpu, parsed_entities.mainboard]:
            if fallback and fallback.strip().lower() != "none":
                lookup_term = fallback
                break
        else:
            lookup_term = search_query

    matched_items = lookup_and_rerank(
        catalog=catalog,
        lookup_term=lookup_term,
        search_query=search_query,
        category=category,
        top_k=3,
        rerank_top_k=2
    )
        
    context = build_product_context(search_query, category, matched_items, include_all_fields=False)
    
    format_hint = ""
    if matched_items:
        item = matched_items[0]
        price_raw = get_field(item, "giá", "price", default=0)
        name_disp = get_field(item, "tên", "name", default=lookup_term)
        price_str = format_currency_vietnam(price_raw)
        format_hint = (
            f"\n[CHỈ THỊ CỦA HỆ THỐNG]: Khách hàng muốn hỏi giá. BẮT BUỘC chỉ trả lời đúng 1 câu ngắn gọn, không giải thích dài dòng: "
            f"\"Dạ, giá của **{name_disp}** hiện tại là **{price_str} VNĐ** ạ.\""
        )
        
    return context, format_hint


def build_budget_search_context(parsed_entities, msg_lower, category, catalog: ShopCatalog, user_message, search_query) -> tuple[str, str]:
    """
    Container xử lý riêng cho luồng tìm kiếm linh kiện theo tầm giá / ngân sách tối đa,
    kèm phân tích Regex động cho khoảng giá (từ X đến Y), top rẻ nhất (asc), đắt nhất (desc).
    Trả về: (context, format_hint)
    """
    brand = detect_brand(msg_lower)
    
    lo = 0.0
    hi = float(parsed_entities.budget_amount) if getattr(parsed_entities, 'budget_amount', 0) > 0 else 999999999.0
    top_k = 5
    sort_order = "none"
    
    # Phân tích Regex trực tiếp từ msg_lower — ưu tiên hơn budget_amount từ LLM (thường sai đơn vị)
    # 1. Từ X đến Y triệu
    m_range = re.search(r'từ\s+(\d+(?:\.\d+)?)\s*(?:triệu|tr)?\s*(?:đến|tới|-)\s*(\d+(?:\.\d+)?)\s*(?:triệu|tr)', msg_lower)
    if m_range:
        lo = float(m_range.group(1)) * 1_000_000
        hi = float(m_range.group(2)) * 1_000_000
    else:
        # 2. Dưới X triệu
        m_under = re.search(r'dưới\s+(\d+(?:\.\d+)?)\s*(?:triệu|tr)', msg_lower)
        if m_under:
            hi = float(m_under.group(1)) * 1_000_000
        else:
            # 3. Tầm / khoảng / cỡ / quanh X triệu (+/- 20%)
            m_around = re.search(r'(?:tầm|khoảng|cỡ|quanh)\s+(\d+(?:\.\d+)?)\s*(?:triệu|tr)', msg_lower)
            if m_around:
                target = float(m_around.group(1)) * 1_000_000
                lo = target * 0.8
                hi = target * 1.2
            elif hi < 100_000:  # LLM trả về đơn vị triệu (VD: 5) thay vì VNĐ (5000000)
                hi = hi * 1_000_000
        
    # 2. Tìm yêu cầu sắp xếp rẻ nhất / đắt nhất
    if any(k in msg_lower for k in ["rẻ nhất", "thấp nhất", "giá rẻ", "giá thấp"]):
        sort_order = "asc"
    elif any(k in msg_lower for k in ["đắt nhất", "cao nhất", "giá cao", "max giá"]):
        sort_order = "desc"
    else:
        sort_order = "desc" # Mặc định lấy sản phẩm tốt nhất (đắt nhất) sát với ngân sách
        
    # 3. Tìm số lượng top K
    m_top = re.search(r'(?:top|cho xem|list|liệt kê)\s+(\d+)', msg_lower)
    if m_top:
        top_k = int(m_top.group(1))
    
    matches = catalog.search_products(ProductQuery(
        text=search_query,
        category=category,
        brand=brand,
        price_min=int(lo),
        price_max=int(hi),
        order=sort_order,
        limit=1000,
    ))
    total_count = len(matches)
    matched_items = [item.as_legacy_dict() for item in matches[:top_k]]
    
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
            
        format_hint += "\n[TUYỆT ĐỐI TUÂN THỦ]: BẠN PHẢI TRỰC TIẾP LIỆT KÊ TÊN VÀ GIÁ TỪNG SẢN PHẨM Ở TRÊN RA CHO KHÁCH. KHÔNG ĐƯỢC LƯỜI BIẾNG GIẤU THÔNG TIN. KHÔNG ĐƯỢC HỎI NGƯỢC LẠI KHÁCH HÀNG MÀ PHẢI ĐƯA RA DANH SÁCH LUÔN."
            
    return context, format_hint