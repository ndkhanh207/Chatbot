"""Unit mapping configuration for product specifications.

This module defines the unit suffixes for various product specification fields,
organized by product category.  It is used by ``chat_handler`` to format
specification values with their appropriate units when building product context
strings.

The structure is a two‑level dictionary:

* **Outer key** – product category (uppercase string, e.g. ``"GPU"``, ``"CPU"``).
  The special key ``"default"`` is used when a category does not have a
  specific override.
* **Inner key** – lower‑cased field name (e.g. ``"xung cơ bản"``, ``"tdp"``).
* **Value** – the unit string to append (e.g. ``"GHz"``, ``"W"``).

To add a new category or override a field's unit, simply add an entry to the
``UNIT_MAP`` dictionary below.
"""

UNIT_MAP: dict[str, dict[str, str]] = {
    "default": {
        'ram tối đa': 'GB',
        'giá': 'VND',
        'tdp': 'W',
        'xung cơ bản': 'GHz',
        'xung boost': 'GHz',
        'kích thước': 'mm',
        'chiều dài': 'mm',
    },
    "GPU": {
        # GPU clock speeds are expressed in megahertz
        'xung cơ bản': 'MHz',
        'xung boost': 'MHz',
        'bộ nhớ': 'GB',
    },
    # Additional categories (e.g., "CPU", "MAINBOARD") can be added
    # here if they need different units for the same field.
}


def get_unit_map(category: str | None) -> dict[str, str]:
    # 1. Lấy toàn bộ đơn vị mặc định làm nền tảng
    merged_map = UNIT_MAP["default"].copy()
    # 2. Nếu category có cấu hình riêng, ghi đè (update) lên nền tảng mặc định
    if category and category in UNIT_MAP:
        merged_map.update(UNIT_MAP[category])
        
    return merged_map
