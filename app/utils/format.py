"""Shared formatting helpers — single source for currency and dict utilities."""

import pandas as pd


def format_currency_vietnam(value) -> str:
    """Format a number as Vietnamese currency with dot separators."""
    try:
        if pd.isna(value) or value == "" or value is None:
            return "0"
        value_int = int(float(value))
        return f"{value_int:,}".replace(",", ".")
    except Exception:
        return "0"


def calculate_total_price(*prices) -> str:
    """Sum prices and return a formatted Vietnamese currency string.

    Skips None, empty, or invalid values.
    Returns formatted total line, or empty string if total is zero.
    """
    total = 0
    for price in prices:
        try:
            if not pd.isna(price) and price != "" and price is not None:
                total += int(float(price))
        except Exception:
            pass

    if total > 0:
        return f"- TỔNG CỘNG DỰ KIẾN: {format_currency_vietnam(total)} VNĐ"
    return ""


def get_field(item: dict, *keys, default=None):
    """Return the first non-empty value from *keys* in *item*."""
    return next((item[k] for k in keys if item.get(k) not in (None, "")), default)
