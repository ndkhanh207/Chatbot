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
        'xung cơ bản': 'GHz',   # CPU default
        'xung boost': 'GHz',
        'kich thước': 'mm',
    },
    "GPU": {
        # GPU clock speeds are expressed in megahertz
        'xung cơ bản': 'MHz',
        'xung boost': 'MHz',
    },
    # Additional categories (e.g., "CPU", "MAINBOARD") can be added
    # here if they need different units for the same field.
}


def get_unit_map(category: str | None) -> dict[str, str]:
    """Return the unit mapping for a given product category.

    If the category has a specific override in ``UNIT_MAP``, that mapping is
    returned.  Otherwise, the ``"default"`` mapping is returned.

    Parameters
    ----------
    category : str | None
        The product category (e.g. ``"GPU"``, ``"CPU"``).  Case‑sensitive.
        If ``None`` or not found, the default mapping is used.

    Returns
    -------
    dict[str, str]
        A dictionary mapping lower‑cased field names to their unit strings.
    """
    if category and category in UNIT_MAP:
        return UNIT_MAP[category]
    return UNIT_MAP["default"]
