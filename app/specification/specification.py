from app.core.search_engine import hybrid_search
from app.specification.context_builder import build_product_context
import pandas as pd
from app.constants import FIELD_KEYWORD_ALIASES

SEARCH_TOP_K = 3
RERANK_TOP_K = 2

def _is_valid_val(val: any) -> bool:
    """Kiểm tra xem giá trị DB có hợp lệ không."""
    if val is None: 
        return False
    if isinstance(val, float) and pd.isna(val): 
        return False
    if isinstance(val, str) and val.strip() == "": 
        return False
    return True

def _find_spec_field(query_lower: str, spec_detail_llm: str, item: dict) -> tuple[str | None, any, str]:
    """Tìm field_key, value, và alias khớp nhất từ câu hỏi người dùng (early return pattern)."""
    best_empty_match = None

    # Bước 1: Quét câu hỏi gốc
    for field_key, aliases in FIELD_KEYWORD_ALIASES.items():
        for alias in aliases:
            if alias in query_lower:
                val = item.get(field_key)
                if _is_valid_val(val):
                    return field_key, val, alias
                if not best_empty_match:
                    best_empty_match = (field_key, val, alias)

    # Bước 2: Fallback dùng LLM spec_detail
    if spec_detail_llm and spec_detail_llm.strip().lower() != "none":
        asked_lower = spec_detail_llm.lower()
        for field_key, aliases in FIELD_KEYWORD_ALIASES.items():
            if asked_lower in aliases or asked_lower == field_key.lower():
                val = item.get(field_key)
                if _is_valid_val(val):
                    return field_key, val, asked_lower
                if not best_empty_match:
                    best_empty_match = (field_key, val, asked_lower)

    # Bước 3: Nếu có match nhưng value rỗng
    if best_empty_match:
        return best_empty_match

    # Bước 4: Nếu không match gì cả
    return None, None, "tất cả thông số"


def build_specification_context(parsed_intent, category, knowledge_base, vector_store, search_query) -> tuple[str, str]:
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

    matched_items = hybrid_search(lookup_term, category, SEARCH_TOP_K, knowledge_base, vector_store) or []

    if not matched_items and lookup_term != search_query:
        matched_items = hybrid_search(search_query, category, SEARCH_TOP_K, knowledge_base, vector_store) or []
    
    if matched_items and len(matched_items) > 1:
        lookup_clean = lookup_term.replace('-', ' ').lower()
        lookup_tokens = [w for w in lookup_clean.split() if len(w) > 1]
        
        def name_match_score(item):
            name = (item.get('tên') or item.get('name') or '').replace('-', ' ').lower()
            exact_bonus = 100 if lookup_clean in name or all(t in name for t in lookup_tokens) else 0
            return exact_bonus + sum(1 for t in lookup_tokens if t in name)
            
        matched_items.sort(key=name_match_score, reverse=True)
        matched_items = matched_items[:RERANK_TOP_K]
    
    context = build_product_context(search_query, category, matched_items, include_all_fields=True)
    
    format_hint = ""
    if matched_items:
        item = matched_items[0]
        actual_name = item.get('tên') or item.get('name') or lookup_term
        
        detected_field_key, detected_field_val, spec_detail = _find_spec_field(
            query_lower=search_query.lower(),
            spec_detail_llm=parsed_intent.spec_detail,
            item=item
        )
        if not detected_field_key:
            spec_detail = "tất cả thông số"

        format_hint = f"THÔNG TIN HỆ THỐNG: Khách đang hỏi thông số '{spec_detail}' của '{actual_name}'."
        
        if detected_field_key:
            if not _is_valid_val(detected_field_val):
                format_hint += f"\n⚠️ LƯU Ý: Thông số '{spec_detail}' của sản phẩm này hiện chưa có trong cơ sở dữ liệu. Hãy trả lời lịch sự rằng bạn chưa có thông tin này."
            else:
                format_hint += f"\n✅ DỮ LIỆU THỰC TẾ: Thông số '{spec_detail}' = '{detected_field_val}'. Hãy trả lời DỰA TRÊN GIÁ TRỊ NÀY, giữ nguyên số và đơn vị."
                    
        format_hint += "\n📌 QUAN TRỌNG: Trả lời phải giữ NGUYÊN giá trị số và đơn vị như trong dữ liệu (VD: VNĐ, MHz). TUYỆT ĐỐI KHÔNG tự tính toán, KHÔNG chuyển đổi đơn vị, và KHÔNG trích dẫn/nhắc lại quy tắc này."
        
    return context, format_hint