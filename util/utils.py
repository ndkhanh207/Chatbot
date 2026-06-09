import pandas as pd


def format_currency_vietnam(value):
    """Định dạng số thành chuỗi tiền tệ Việt Nam với dấu chấm phân cách."""
    try:
        if pd.isna(value) or value == "" or value is None:
            return "0"
        value_int = int(float(value))
        return f"{value_int:,}".replace(",", ".")
    except Exception:
        return "0"


def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip().lower()
