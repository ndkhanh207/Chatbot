from app.compact.pricing import format_currency_vietnam, calculate_total_price
from app.compact.compat_logic import _get_field

def _fmt_cpu_main(cpu: dict, main: dict, check: dict) -> str:
    cpu_price = _get_field(cpu, 'giá', 'price', default=None)
    main_price = _get_field(main, 'giá', 'price', default=None)
    cpu_price_str = f" | Giá: {format_currency_vietnam(cpu_price)} VNĐ" if cpu_price else ""
    main_price_str = f" | Giá: {format_currency_vietnam(main_price)} VNĐ" if main_price else ""
    verdict = "CÓ THỂ LẮP ĐƯỢC (TƯƠNG THÍCH)" if check['is_compatible'] else "KHÔNG LẮP ĐƯỢC (KHÔNG TƯƠNG THÍCH)"
    
    total_str = calculate_total_price(cpu_price, main_price)

    lines = [
        "[KẾT QUẢ THẨM ĐỊNH TƯƠNG THÍCH CPU - MAINBOARD]",
        f"- CPU: '{_get_field(cpu, 'tên', 'name', default='')}'{cpu_price_str}",
        f"- Mainboard: '{_get_field(main, 'tên', 'name', default='')}' "
        f"(Chipset: {check.get('chipset') or 'không rõ'}){main_price_str}",
    ]
    if total_str:
        lines.append(total_str)
    lines.append(f"- KẾT LUẬN KỸ THUẬT: {verdict}")
    return "\n".join(lines + [f"- {r}" for r in check["reasons"]]) + "\n"


def _fmt_gpu_main(gpu: dict, main: dict, check: dict) -> str:
    gpu_price = _get_field(gpu, 'giá', 'price', default=None)
    main_price = _get_field(main, 'giá', 'price', default=None)
    gpu_price_str = f" | Giá: {format_currency_vietnam(gpu_price)} VNĐ" if gpu_price else ""
    main_price_str = f" | Giá: {format_currency_vietnam(main_price)} VNĐ" if main_price else ""
    
    total_str = calculate_total_price(gpu_price, main_price)

    lines = [
        "[KẾT QUẢ THẨM ĐỊNH TƯƠNG THÍCH GPU - MAINBOARD]",
        f"- GPU: '{_get_field(gpu, 'tên', 'name', default='')}' (PCIe: {check.get('gpu_pcie_gen') or '?'}){gpu_price_str}",
        f"- Mainboard: '{_get_field(main, 'tên', 'name', default='')}' (PCIe: {check.get('main_pcie_gen') or '?'}){main_price_str}",
    ]
    if total_str:
        lines.append(total_str)
    lines.append("- KẾT LUẬN KỸ THUẬT: CÓ THỂ LẮP ĐƯỢC (PCIe tương thích ngược/xuôi).")
    if check.get("warning"):
        lines.append(f"- CẢNH BÁO: {check['warning']}")
    return "\n".join(lines) + "\n"


def _fmt_cpu_gpu(cpu: dict, gpu: dict, check: dict) -> str:
    cpu_price = _get_field(cpu, 'giá', 'price', default=None)
    gpu_price = _get_field(gpu, 'giá', 'price', default=None)
    cpu_price_str = f" | Giá: {format_currency_vietnam(cpu_price)} VNĐ" if cpu_price else ""
    gpu_price_str = f" | Giá: {format_currency_vietnam(gpu_price)} VNĐ" if gpu_price else ""
    
    total_str = calculate_total_price(cpu_price, gpu_price)

    lines = [
        "[KẾT QUẢ ĐÁNH GIÁ CẶP CPU - GPU]",
        f"- CPU: '{_get_field(cpu, 'tên', 'name', default='')}'{cpu_price_str}",
        f"- GPU: '{_get_field(gpu, 'tên', 'name', default='')}'{gpu_price_str}",
    ]
    if total_str:
        lines.append(total_str)
    lines.append("- KẾT LUẬN KỸ THUẬT: PHÙ HỢP (không có giới hạn lắp đặt giữa CPU-GPU).")
    if check.get("warning"):
        lines.append(f"- LƯU Ý: {check['warning']}")
    return "\n".join(lines) + "\n"
