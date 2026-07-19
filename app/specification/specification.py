from app.catalog import ProductQuery, ShopCatalog
from app.catalog.context_builder import build_product_context
import pandas as pd
from app.constants import FIELD_KEYWORD_ALIASES

SEARCH_TOP_K = 3
RERANK_TOP_K = 2
import re

def _is_valid_val(val: any) -> bool:
    """Kiểm tra xem giá trị DB có hợp lệ không."""
    if val is None: 
        return False
    if isinstance(val, (int, float)) and val == 0:
        return False
    if isinstance(val, float) and pd.isna(val): 
        return False
    if isinstance(val, str) and val.strip() == "": 
        return False
    return True

def _find_spec_field(query_lower: str, spec_detail_llm: str, item: dict) -> tuple[str | None, any, str]:
    """Tìm field_key, value, và alias khớp nhất từ câu hỏi người dùng (early return pattern)."""
    best_empty_match = None
    print(f"DEBUG: query_lower='{query_lower}', spec_detail_llm='{spec_detail_llm}'", flush=True)

    # Bước 1: Quét câu hỏi gốc
    for field_key, aliases in FIELD_KEYWORD_ALIASES.items():
        for alias in aliases:
            if alias in query_lower:
                val = item.get(field_key)
                valid = _is_valid_val(val)
                print(f"DEBUG Step 1: matched alias='{alias}' for field='{field_key}', val='{val}', valid={valid}", flush=True)
                if valid:
                    return field_key, val, alias
                if not best_empty_match:
                    best_empty_match = (field_key, val, alias)

    # Bước 2: Fallback dùng LLM spec_detail
    if spec_detail_llm and spec_detail_llm.strip().lower() != "none":
        asked_lower = spec_detail_llm.lower()
        print(f"DEBUG Step 2: checking spec_detail_llm='{asked_lower}'", flush=True)
        for field_key, aliases in FIELD_KEYWORD_ALIASES.items():
            if asked_lower in aliases or asked_lower == field_key.lower():
                val = item.get(field_key)
                valid = _is_valid_val(val)
                print(f"DEBUG Step 2: matched field='{field_key}', val='{val}', valid={valid}", flush=True)
                if valid:
                    return field_key, val, asked_lower
                if not best_empty_match:
                    best_empty_match = (field_key, val, asked_lower)

    # Bước 3: Nếu có match nhưng value rỗng
    if best_empty_match:
        return best_empty_match

    # Bước 4: Nếu không match gì cả
    return None, None, "tất cả thông số"


def _is_generic_clock_question(query_lower: str, spec_detail_llm: str) -> bool:
    asked = f"{query_lower} {spec_detail_llm or ''}".lower()
    if any(term in asked for term in ["xung boost", "boost clock", "xung cơ bản", "base clock"]):
        return False
    return any(term in asked for term in ["xung nhịp", "xung", "tốc độ"])


def _build_clock_hint(item: dict) -> str:
    base_clock = item.get("xung cơ bản")
    boost_clock = item.get("xung boost")
    if not (_is_valid_val(base_clock) and _is_valid_val(boost_clock)):
        return ""
    return (
        "DỮ LIỆU THỰC TẾ: xung cơ bản = "
        f"'{base_clock} MHz', xung boost = '{boost_clock} MHz'. "
        "Hãy trả lời đúng cả 2 giá trị này, giữ nguyên số và đơn vị. "
        "Không thêm Lý do, không nhắc hệ thống/dữ liệu."
    )


def build_specification_context(parsed_intent, category, catalog: ShopCatalog, search_query) -> tuple[str, str]:
    """
    Container xử lý riêng cho luồng hỏi thông số kỹ thuật.
    Trả về: (context, format_hint)
    """
    lookup_term = parsed_intent.target_product
    if not lookup_term or lookup_term.strip().lower() == "none":
        for fallback in [parsed_intent.cpu, parsed_intent.gpu, parsed_intent.mainboard]:
            if fallback and fallback.strip().lower() != "none":
                lookup_term = fallback
                break
        else:
            lookup_term = search_query

    from app.catalog.lookup import lookup_and_rerank
    matched_items = lookup_and_rerank(
        catalog=catalog,
        lookup_term=lookup_term,
        search_query=search_query,
        category=category,
        top_k=SEARCH_TOP_K,
        rerank_top_k=RERANK_TOP_K
    )
    
    context = build_product_context(search_query, category, matched_items, include_all_fields=True)
    
    format_hint = ""
    if matched_items:
        item = matched_items[0]
        actual_name = item.get('tên') or item.get('name') or lookup_term
        query_lower = search_query.lower()

        detected_field_key, detected_field_val, spec_detail = _find_spec_field(
            query_lower=query_lower,
            spec_detail_llm=parsed_intent.spec_detail,
            item=item
        )
        has_open_spec_detail = parsed_intent.spec_detail and parsed_intent.spec_detail.strip().lower() != "none"
        if not detected_field_key:
            spec_detail = parsed_intent.spec_detail if has_open_spec_detail else "tất cả thông số"

        format_hint = f"THÔNG TIN HỆ THỐNG: Khách đang hỏi thông số '{spec_detail}' của '{actual_name}'."
        clock_hint = _build_clock_hint(item) if _is_generic_clock_question(query_lower, parsed_intent.spec_detail) else ""
        
        if clock_hint:
            format_hint += f"\n{clock_hint}"
            format_hint += "\nQUAN TRỌNG: Chỉ trả lời thẳng vào thông tin số liệu. Giữ nguyên đơn vị. KHÔNG giải thích thêm."
        elif detected_field_key:
            if not _is_valid_val(detected_field_val):
                format_hint += f"\nLƯU Ý: Thông số '{spec_detail}' của sản phẩm này hiện chưa có trong cơ sở dữ liệu. Hãy trả lời lịch sự rằng bạn chưa có thông tin này."
            else:
                format_hint += f"\nDỮ LIỆU THỰC TẾ: Thông số '{spec_detail}' = '{detected_field_val}'.\n[BẮT BUỘC]: Bê nguyên si giá trị '{detected_field_val}' vào câu trả lời. KHÔNG ngoại suy, KHÔNG thêm đơn vị nếu không có, KHÔNG bịa thêm chữ, KHÔNG giải thích ý nghĩa, KHÔNG dịch sang tiếng Anh hay tiếng Trung."
                    
            format_hint += "\nQUAN TRỌNG: Chỉ trả lời thẳng vào thông tin số liệu. TRẢ LỜI CÀNG NGẮN CÀNG TỐT."
        elif has_open_spec_detail:
            format_hint += "\nQUAN TRỌNG: Đây là câu hỏi tư vấn theo thuộc tính/nhu cầu không có cột dữ liệu trực tiếp trong DB."
            format_hint += "\nHãy dùng dữ liệu sản phẩm trong context và kiến thức chung của bạn để trả lời ngắn, đúng câu hỏi. Nếu thiếu điều kiện phụ (CPU/RAM/độ phân giải...) thì nhắc thật ngắn, không hỏi vặn."
        else:
            format_hint += "\nQUAN TRỌNG: Hãy liệt kê trực tiếp các thông số kỹ thuật của sản phẩm dưới dạng danh sách gạch đầu dòng (bullet points). TUYỆT ĐỐI KHÔNG GIẢI THÍCH ý nghĩa của bất kỳ thông số nào (ví dụ: không giải thích TPU là gì, kiến trúc là gì). KHÔNG TỰ BỊA THÊM THÔNG SỐ ngoài [DỮ LIỆU THỰC TẾ], và TUYỆT ĐỐI KHÔNG TỰ ĐỘNG QUY ĐỔI ĐƠN VỊ (Ví dụ: phải giữ nguyên MHz)."
        
        format_hint += "\n[TUYỆT ĐỐI TUÂN THỦ]: TRẢ LỜI NGẮN GỌN TỐI ĐA. KHÔNG yapping, KHÔNG chào hỏi dài dòng, KHÔNG phân tích, KHÔNG kết luận thừa thãi."
        
    return context, format_hint

def build_general_search_context(parsed_intent, msg_lower, category, catalog: ShopCatalog, search_query) -> tuple[str, str]:
    """
    Container xử lý riêng cho luồng tìm kiếm chung chung (general_search).
    Hỗ trợ Regex lấy số lượng (ví dụ: "top 5").
    """
    top_k = 4
    m_top = re.search(r'(?:top|cho xem|list|liệt kê)\s+(\d+)', msg_lower)
    if m_top:
        top_k = min(int(m_top.group(1)), 10)
        
    # q_clean was used in chat_handler, but search_query is essentially q_clean or very close. 
    # To be exactly identical, we will just use search_query here.
    matched_items = [item.as_legacy_dict() for item in catalog.search_products(
        ProductQuery(text=search_query, category=category, limit=top_k)
    )]
    context = build_product_context(search_query, category, matched_items, include_all_fields=False)
    
    return context, ""
