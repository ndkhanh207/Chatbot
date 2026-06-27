"""
price_calculator.py
Module độc lập xử lý yêu cầu TÍNH TỔNG GIÁ linh kiện.
LLM bóc tách tên linh kiện → Python tra DB lấy giá → cộng tổng cứng (không dùng LLM tính toán).
"""

from app.core.search_engine import hybrid_search
from app.core.master_intent import MasterIntentSchema
from app.compatibility.compat_logic import _get_field
from app.price.pricing_util import format_currency_vietnam

# Trigger từ khóa mồi để gọi luồng tính giá
PRICE_CALCULATION_TRIGGERS = [
    'tổng giá', 'tổng cộng', 'tổng chi phí', 'tổng tiền',
    'tất cả bao nhiêu', 'hết bao nhiêu',
]

def is_price_calculation_query(message: str) -> bool:
    """Gate nhận diện câu hỏi tính tổng giá — tách khỏi is_compatibility_query."""
    return any(t in message for t in PRICE_CALCULATION_TRIGGERS)


def _resolve_item(name: str, category: str, knowledge_base, vector_store):
    """Tra cứu 1 linh kiện trong DB. Trả về None nếu 'none'/rỗng hoặc không tìm thấy."""
    if not name or name.strip().lower() == "none":
        return None
    normalized = name.lower().replace("-", " ")
    results = hybrid_search(normalized, category, 1, knowledge_base, vector_store)
    return results[0] if results else None


def build_price_calculation_context(intent: MasterIntentSchema, knowledge_base, vector_store) -> str:
    """
    Xây dựng context tính tổng giá cho các linh kiện đã được LLM bóc tách.
    Giá được lấy từ DB và cộng bằng Python — KHÔNG để LLM tự tính.
    """
    cpu  = _resolve_item(intent.cpu,       "CPU",       knowledge_base, vector_store)
    main = _resolve_item(intent.mainboard, "MAINBOARD", knowledge_base, vector_store)
    gpu  = _resolve_item(intent.gpu,       "GPU",       knowledge_base, vector_store)

    lines         = ["[KẾT QUẢ TÍNH TỔNG GIÁ LINH KIỆN]"]
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
            price_raw = _get_field(item, "giá", "price", default=0)
            try:
                price_val = int(float(price_raw)) if price_raw else 0
            except Exception:
                price_val = 0
            total_price += price_val
            name_disp = _get_field(item, "tên", "name", default=item_name)
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
