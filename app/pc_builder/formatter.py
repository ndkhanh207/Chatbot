# app/pc_builder/formatter.py

def format_approx_million(vnd: float) -> str:
    """
    Chuyển giá VNĐ sang dạng xấp xỉ triệu đồng.
    Ví dụ: 25_250_500 → "~25.3 triệu"
    """
    try:
        millions = round(float(vnd) / 1_000_000, 1)
        if millions == int(millions):
            return f"~{int(millions)} triệu"
        return f"~{millions} triệu"
    except (TypeError, ValueError):
        return "N/A"

def format_build_context(build: dict) -> str:
    """
    Chuyển dict bộ PC thành chuỗi context để inject vào prompt.
    """
    if not build:
        return ""

    total_price  = format_approx_million(build.get('Total_Price', 0))
    cpu_price    = format_approx_million(build.get('Component_Price_CPU', 0))
    gpu_price    = format_approx_million(build.get('Component_Price_GPU', 0))
    main_price   = format_approx_million(build.get('Component_Price_Motherboard', 0))
    assembly_fee = format_approx_million(build.get('Assembly_Fee', 0))

    return (
        f"[GỢI Ý BỘ PC TỐI ƯU]\n"
        f"- Mã bộ     : {build.get('BuildID', 'N/A')}\n"
        f"- CPU       : {build.get('CPU_Model', 'N/A')} | Giá: {cpu_price}\n"
        f"- GPU       : {build.get('GPU_Model', 'N/A')} | Giá: {gpu_price}\n"
        f"- Mainboard : {build.get('Motherboard_Model', 'N/A')} | Giá: {main_price}\n"
        f"- Phí lắp ráp: {assembly_fee}\n"
        f"- Tổng cộng : {total_price}\n"
        f"- Phù hợp cho: {build.get('Build_Notes', '')}\n"
    )

def format_reply_body(best_build: dict, budget: int, purpose_str: str, quantity: int = 1) -> str:
    """Format phần thân câu trả lời."""
    cpu_model      = best_build.get('CPU_Model', 'N/A')
    cpu_price      = format_approx_million(best_build.get('Component_Price_CPU', 0))
    gpu_model      = best_build.get('GPU_Model', 'N/A')
    gpu_price      = format_approx_million(best_build.get('Component_Price_GPU', 0))
    main_model     = best_build.get('Motherboard_Model', 'N/A')
    main_price     = format_approx_million(best_build.get('Component_Price_Motherboard', 0))
    total_price    = format_approx_million(best_build.get('Total_Price', 0))
    assembly_price = format_approx_million(best_build.get('Assembly_Fee', 200_000))
    build_id       = best_build.get('BuildID', 'N/A')
    budget_str     = format_approx_million(budget) if budget > 0 else 'rẻ nhất'

    qty_note = f" (×{quantity} bộ = {format_approx_million(best_build.get('Total_Price', 0) * quantity)})" \
               if quantity > 1 else ""

    return (
        f"[GỢI Ý BỘ PC TỐI ƯU]\n"
        f"- Mã bộ: {build_id}\n\n"
        f"Xin chào, tôi rất vui được giúp bạn xây dựng một máy tính để {purpose_str} hiệu quả! "
        f"Bạn muốn sử dụng bộ PC này cho {purpose_str} và có ngân sách khoảng {budget_str}.\n\n"
        f"Bộ PC của bạn sẽ bao gồm các thành phần sau:\n\n"
        f"- CPU: {cpu_model}, giá {cpu_price}\n"
        f"- GPU: {gpu_model}, giá {gpu_price}\n"
        f"- Mainboard: {main_model}, giá {main_price}\n"
        f"- Phí lắp ráp: {assembly_price}\n\n"
        f"Tổng cộng chi phí cho các thành phần này là khoảng {total_price}{qty_note}."
    )
