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

def calculate_total_price(*prices) -> str:
    """
    Cộng tổng các mức giá đầu vào và trả về chuỗi định dạng tiền Việt Nam.
    Bỏ qua các giá trị None, rỗng, hoặc không hợp lệ.
    Trả về chuỗi báo tổng giá, ví dụ: '- TỔNG CỘNG DỰ KIẾN: 10.000.000 VNĐ'
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
