import re
from app.constants import FIELD_KEYWORD_ALIASES
from app.price.pricing_util import format_currency_vietnam
from app.utils.unit_converter import CONVERSIONS, convert_if_needed, ALIASES
from app.utils.units import get_unit_map

def field_relevance_score(field_name: str, msg_lower: str) -> int:
    field_lower = field_name.lower()
    if field_lower in msg_lower:
        return 2
    for alias in FIELD_KEYWORD_ALIASES.get(field_lower, []):
        if alias in msg_lower:
            return 2
    return 0

def build_product_context(user_message: str, category: str | None, matched_items: list, include_all_fields: bool = False) -> str:
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

    wants_all_specs = include_all_fields or any(w in msg_lower for w in ["thông số", "chi tiết", "cấu hình", "specs", "đặc điểm", "toàn bộ"])

    lines = ["Dạ, danh sách linh kiện thực tế đang có sẵn tại cửa hàng:"]
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
                    str_val = str(val).strip()
                    if str_val.lower().endswith(unit.lower()):
                        formatted_value = f"{key}: {val}"
                    else:
                        formatted_value = f"{key}: {val} {unit}"
                    field_entries.append((
                        field_relevance_score(key, msg_lower),
                        index, formatted_value, [],
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
        
        # Chỉ hiển thị giá nếu người dùng hỏi, hoặc nếu đây là tìm kiếm chung chung (extra_parts rỗng)
        show_price = wants_all_specs or any(k in msg_lower for k in ["giá", "tiền", "budget", "ngân sách", "rẻ", "đắt", "vnd", "vnđ"])
        if not extra_parts:
            show_price = True
            
        price_str = f" | **Giá:** {p_format} VNĐ" if show_price else ""
        
        lines.append(
            f"- **[{item.get('category')}]** {name}{price_str}{extra}"
        )

    return "\n".join(lines)