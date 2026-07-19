"""
price_calculator.py
Module độc lập xử lý yêu cầu TÍNH TỔNG GIÁ linh kiện.
LLM bóc tách tên linh kiện → Python tra DB lấy giá → cộng tổng cứng (không dùng LLM tính toán).
"""

from app.catalog import ShopCatalog, resolve_component
from app.core.intent.master_intent import MasterIntentSchema
from app.utils.format import get_field, format_currency_vietnam

# Trigger từ khóa mồi để gọi luồng tính giá
PRICE_CALCULATION_TRIGGERS = [
    'tổng giá', 'tổng cộng', 'tổng chi phí', 'tổng tiền',
    'tất cả bao nhiêu', 'hết bao nhiêu',
]

def is_price_calculation_query(message: str) -> bool:
    """Gate nhận diện câu hỏi tính tổng giá — tách khỏi is_compatibility_query."""
    return any(t in message for t in PRICE_CALCULATION_TRIGGERS)


def build_price_calculation_context(intent: MasterIntentSchema, catalog: ShopCatalog) -> str:
    """Xây dựng context tính tổng giá cho các linh kiện đã được LLM bóc tách.
    Giá được lấy từ DB và cộng bằng Python — KHÔNG để LLM tự tính."""
    cpu  = resolve_component(intent.cpu,       "CPU",       catalog)
    main = resolve_component(intent.mainboard, "MAINBOARD", catalog)
    gpu  = resolve_component(intent.gpu,       "GPU",       catalog)

    lines         = ["Dạ, chi tiết giá các linh kiện anh/chị cần tính đây ạ:\n"]
    total_price   = 0
    found_items   = []
    missing_items = []

    for item_name, item, category in [
        (intent.cpu,       cpu,  "CPU"),
        (intent.mainboard, main, "MAINBOARD"),
        (intent.gpu,       gpu,  "GPU"),
    ]:
        if not item_name or item_name.strip().lower() == "none":
            continue
        if item:
            price_raw = get_field(item, "giá", "price", default=0)
            try:
                price_val = int(float(price_raw)) if price_raw else 0
            except Exception:
                price_val = 0
            total_price += price_val
            name_disp = get_field(item, "tên", "name", default=item_name)
            lines.append(f"- [{category}] '{name_disp}' | Giá: {format_currency_vietnam(price_raw)} VNĐ")
            found_items.append(category)
        else:
            missing_items.append(f"{category} '{item_name}'")

    if missing_items:
        lines.append(f"- CẢNH BÁO: Cửa hàng không có dữ liệu cho: {', '.join(missing_items)}.")

    lines.append(
        f"=> TỔNG GIÁ DỰ KIẾN (cho {len(found_items)} linh kiện đã tìm thấy): "
        f"{format_currency_vietnam(total_price)} VNĐ"
    )
    return "\n".join(lines) + "\n"
