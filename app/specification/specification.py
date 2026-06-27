from app.core.search_engine import hybrid_search
from app.specification.context_builder import build_product_context
import pandas as pd
from app.constants import FIELD_KEYWORD_ALIASES

def build_specification_context(parsed_intent, category, knowledge_base, vector_store, search_query) -> tuple[str, str]:
    """
    Container xử lý riêng cho luồng hỏi thông số kỹ thuật.
    Trả về: (context, format_hint)
    """
    # Ưu tiên target_product từ LLM, nhưng nếu LLM bị "ngáo" (trả "none")
    # thì fallback về search_query (câu hỏi gốc đã reformulate, luôn chứa tên SP)
    lookup_term = parsed_intent.target_product
    if not lookup_term or lookup_term.strip().lower() == "none":
        # Thử lấy từ cpu/gpu/mainboard fields trước khi fallback search_query
        for fallback in [parsed_intent.cpu, parsed_intent.gpu, parsed_intent.mainboard]:
            if fallback and fallback.strip().lower() != "none":
                lookup_term = fallback
                break
        else:
            lookup_term = search_query

    matched_items = hybrid_search(
        lookup_term, 
        category, 
        3, 
        knowledge_base,
        vector_store
    ) or []
    
    # Re-rank: ưu tiên sản phẩm có tên chứa nhiều token của lookup_term nhất
    if matched_items and len(matched_items) > 1:
        lookup_clean = lookup_term.replace('-', ' ').lower()
        lookup_tokens = [w for w in lookup_clean.split() if len(w) > 1]
        def name_match_score(item):
            name = (item.get('tên') or item.get('name') or '').replace('-', ' ').lower()
            exact_bonus = 100 if lookup_clean in name or all(t in name for t in lookup_tokens) else 0
            return exact_bonus + sum(1 for t in lookup_tokens if t in name)
        matched_items.sort(key=name_match_score, reverse=True)
        matched_items = matched_items[:2]
    
    context = build_product_context(search_query, category, matched_items, include_all_fields=True)
    
    format_hint = ""
    if matched_items:
        # Lấy tên thực tế từ DB thay vì tin LLM (phòng trường hợp LLM trả "none")
        actual_name = matched_items[0].get('tên') or matched_items[0].get('name') or lookup_term
        item = matched_items[0]
        query_lower = search_query.lower()
        item_cat = str(item.get('category') or category or '').upper()
        
        def is_field_valid_for_category(f_key, cat):
            if cat == 'MAINBOARD' and f_key == 'interface':
                return False  # Mainboard dùng pcie/lưu trữ/khe M.2, không dùng interface
            if cat == 'GPU' and f_key in ['pcie', 'lưu trữ', 'khe M.2', 'khe ram', 'ram tối đa', 'socket']:
                return False  # GPU dùng interface, không dùng pcie/lưu trữ/khe M.2
            if cat == 'CPU' and f_key in ['pcie', 'lưu trữ', 'khe M.2', 'khe ram', 'ram tối đa', 'interface', 'kích thước']:
                return False
            return True

        # Nếu LLM không xác định được spec_detail, tự detect từ câu hỏi gốc
        # bằng cách quét FIELD_KEYWORD_ALIASES
        spec_detail = parsed_intent.spec_detail
        detected_field_key = None
        detected_field_val = None

        if not spec_detail or spec_detail.strip().lower() == "none":
            for field_key, aliases in FIELD_KEYWORD_ALIASES.items():
                if not is_field_valid_for_category(field_key, item_cat):
                    continue
                if any(alias in query_lower for alias in aliases):
                    detected_field_key = field_key
                    detected_field_val = item.get(field_key)
                    spec_detail = field_key  # override spec_detail thành tên field thực
                    break
            if not detected_field_key:
                spec_detail = "all"
        else:
            # LLM có trả spec_detail → tìm field tương ứng
            asked_lower = spec_detail.lower()
            for field_key, aliases in FIELD_KEYWORD_ALIASES.items():
                if not is_field_valid_for_category(field_key, item_cat):
                    continue
                if asked_lower in aliases or asked_lower == field_key.lower():
                    detected_field_key = field_key
                    detected_field_val = item.get(field_key)
                    break
            
            # Nếu LLM trả spec_detail sai/không khớp field nào (như "giá bán"), tự quét lại từ câu hỏi gốc!
            if not detected_field_key:
                for field_key, aliases in FIELD_KEYWORD_ALIASES.items():
                    if not is_field_valid_for_category(field_key, item_cat):
                        continue
                    if any(alias in query_lower for alias in aliases):
                        detected_field_key = field_key
                        detected_field_val = item.get(field_key)
                        spec_detail = field_key
                        break

        format_hint = f"THÔNG TIN HỆ THỐNG: Khách đang hỏi thông số '{spec_detail}' của '{actual_name}'."
        
        if detected_field_key:
            if detected_field_val is None or (isinstance(detected_field_val, float) and pd.isna(detected_field_val)) or (isinstance(detected_field_val, str) and detected_field_val.strip() == ""):
                format_hint += f"\n⚠️ LƯU Ý: Thông số '{detected_field_key}' của sản phẩm này chưa được cập nhật trong cơ sở dữ liệu. Hãy trả lời khách rằng thông tin này chưa có."
            else:
                # Inject trực tiếp giá trị để LLM không phỏng đoán sai
                format_hint += f"\n✅ DỮ LIỆU THỰC TẾ: Thông số '{detected_field_key}' = '{detected_field_val}'. Hãy trả lời DỰA TRÊN GIÁ TRỊ NÀY, giữ nguyên số và đơn vị."
                    
        format_hint += "\n📌 QUAN TRỌNG: Trả lời phải giữ NGUYÊN giá trị số và đơn vị hoa/thường chuẩn mực như trong dữ liệu (VD: ghi đúng 'VNĐ' không ghi 'VND', giữ nguyên 'MHz' không đổi thành 'GHz', giữ nguyên phần thập phân)."
        
    return context, format_hint