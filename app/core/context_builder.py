import re
from app.constants import FIELD_KEYWORD_ALIASES
from app.price.pricing import format_currency_vietnam
from tool.calculator import CONVERSIONS, convert_if_needed, ALIASES
from unit.unit import get_unit_map

def field_relevance_score(field_name: str, msg_lower: str) -> int:
    field_lower = field_name.lower()
    if field_lower in msg_lower:
        return 2
    for alias in FIELD_KEYWORD_ALIASES.get(field_lower, []):
        if alias in msg_lower:
            return 2
    return 0

def build_product_context(user_message: str, category: str | None, matched_items: list) -> str:
    """Build product listing string từ matched_items đã fetch sẵn."""
    if not matched_items or not isinstance(matched_items, list):
        return ""

    msg_lower = user_message.lower()
    requested_unit = None
    for unit in CONVERSIONS.keys():
        if re.search(rf"\b{re.escape(unit.lower())}\b", msg_lower):
            requested_unit = unit
            break
    if not requested_unit:
        for alias, canonical in ALIASES.items():
            if alias.lower() in msg_lower:
                requested_unit = canonical
                break

    wants_all_specs = any(w in msg_lower for w in ["thông số", "chi tiết", "cấu hình", "specs", "đặc điểm", "toàn bộ"])

    lines = ["Danh sách linh kiện thực tế đang có sẵn tại cửa hàng:"]
    for item in matched_items:
        p_format = item.get('price_formatted') or format_currency_vietnam(
            item.get('giá') if 'giá' in item else item.get('price', 0)
        )
        name = item.get('tên') or item.get('name')
        exclude_keys = {
            'category', 'tên', 'name', 'giá', 'price',
            'price_formatted', 'search_text',
        }
        field_entries = []
        current_unit_map = get_unit_map(category)

        for index, (key, val) in enumerate(item.items()):
            if key in exclude_keys or val is None:
                continue
            try:
                import pandas as pd
                if pd.isna(val):
                    continue
            except Exception:
                pass
            if str(val).strip() == "" or (isinstance(val, (int, float)) and val == 0):
                continue

            lower_key = key.lower()
            if lower_key in current_unit_map:
                unit = current_unit_map[lower_key]
                if isinstance(val, (int, float)):
                    formatted_value = f"{key}: {val} {unit}"
                    conversions = convert_if_needed(val, unit, requested_unit)
                    field_entries.append((
                        field_relevance_score(key, msg_lower),
                        index, formatted_value, conversions,
                    ))
                else:
                    field_entries.append((
                        field_relevance_score(key, msg_lower),
                        index, f"{key}: {val}", [],
                    ))
            else:
                field_entries.append((
                    field_relevance_score(key, msg_lower),
                    index, f"{key}: {val}", [],
                ))

        field_entries.sort(key=lambda x: (-x[0], x[1]))
        extra_parts = []
        for score, _, entry, conversions in field_entries:
            if wants_all_specs or score > 0:
                extra_parts.append(entry)
                extra_parts.extend(conversions)

        extra = (' | ' + ' | '.join(extra_parts)) if extra_parts else ''
        lines.append(
            f"- [{item.get('category')}] {name} | Giá: {p_format} VNĐ{extra}"
        )

    return "\n".join(lines)


def filter_knowledge_base_by_price(knowledge_base, category, lo, hi, brand=None, top_k=10):
    """
    Lọc TRỰC TIẾP trên toàn bộ knowledge_base (DataFrame) theo khoảng giá,
    không phụ thuộc vào kết quả semantic search top_k.
    Trả về (list[dict], total_count).
    """
    df = knowledge_base
    price_col = "giá" if "giá" in df.columns else "price"

    mask = (df[price_col] >= lo) & (df[price_col] <= hi)
    if category and "category" in df.columns:
        mask &= (df["category"] == category)

    if brand:
        search_col = "chipset" if "chipset" in df.columns else (
            "tên" if "tên" in df.columns else "name"
        )
        mask &= df[search_col].str.contains(brand, case=False, na=False)

    full_match = df[mask]
    if full_match.empty:
        return [], 0

    total_count = len(full_match)
    sorted_df = full_match.sort_values(by=price_col)

    if total_count <= top_k:
        sample = sorted_df
    else:
        step = max(1, total_count // top_k)
        sample = sorted_df.iloc[::step].head(top_k)

    return sample.to_dict(orient="records"), total_count
