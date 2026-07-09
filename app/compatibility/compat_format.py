from app.price.pricing_util import format_currency_vietnam, calculate_total_price
from app.compatibility.compat_logic import _get_field

def _fmt_cpu_main(cpu: dict, main: dict, check: dict) -> str:
    cpu_price = _get_field(cpu, 'giá', 'price', default=None)
    main_price = _get_field(main, 'giá', 'price', default=None)
    cpu_price_str = f" | Giá: {format_currency_vietnam(cpu_price)} VNĐ" if cpu_price else ""
    main_price_str = f" | Giá: {format_currency_vietnam(main_price)} VNĐ" if main_price else ""
    verdict = "TƯƠNG THÍCH (PHÙ HỢP)" if check['is_compatible'] else "KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP)"
    
    total_str = calculate_total_price(cpu_price, main_price)

    lines = [
        f"- CPU: '{_get_field(cpu, 'tên', 'name', default='')}'{cpu_price_str}",
        f"- Mainboard: '{_get_field(main, 'tên', 'name', default='')}' (Chipset: {check.get('chipset') or 'không rõ'}){main_price_str}",
    ]
    if total_str:
        lines.append(total_str)
    lines.append(f"- KẾT LUẬN TƯƠNG THÍCH: {verdict}")
    return "\n".join(lines + [f"- CHI TIẾT: {r}" for r in check["reasons"]]) + "\n"


def _fmt_gpu_main(gpu: dict, main: dict, check: dict) -> str:
    gpu_price = _get_field(gpu, 'giá', 'price', default=None)
    main_price = _get_field(main, 'giá', 'price', default=None)
    gpu_price_str = f" | Giá: {format_currency_vietnam(gpu_price)} VNĐ" if gpu_price else ""
    main_price_str = f" | Giá: {format_currency_vietnam(main_price)} VNĐ" if main_price else ""
    
    total_str = calculate_total_price(gpu_price, main_price)

    lines = [
        f"- GPU: '{_get_field(gpu, 'tên', 'name', default='')}' (PCIe: {check.get('gpu_pcie_gen') or '?'}){gpu_price_str}",
        f"- Mainboard: '{_get_field(main, 'tên', 'name', default='')}' (PCIe: {check.get('main_pcie_gen') or '?'}){main_price_str}",
    ]
    if total_str:
        lines.append(total_str)
    lines.append("- KẾT LUẬN TƯƠNG THÍCH: TƯƠNG THÍCH (PHÙ HỢP)")
    if check.get("warning"):
        lines.append(f"- CẢNH BÁO BĂNG THÔNG: {check['warning']}")
    return "\n".join(lines) + "\n"


def _fmt_cpu_gpu(cpu: dict, gpu: dict, check: dict) -> str:
    cpu_price = _get_field(cpu, 'giá', 'price', default=None)
    gpu_price = _get_field(gpu, 'giá', 'price', default=None)
    cpu_price_str = f" | Giá: {format_currency_vietnam(cpu_price)} VNĐ" if cpu_price else ""
    gpu_price_str = f" | Giá: {format_currency_vietnam(gpu_price)} VNĐ" if gpu_price else ""
    
    total_str = calculate_total_price(cpu_price, gpu_price)

    lines = [
        f"- CPU: '{_get_field(cpu, 'tên', 'name', default='')}'{cpu_price_str}",
        f"- GPU: '{_get_field(gpu, 'tên', 'name', default='')}'{gpu_price_str}",
    ]
    if total_str:
        lines.append(total_str)
        
    if check.get("warning"):
        lines.append(f"- CẢNH BÁO QUAN TRỌNG: Cấu hình này CÓ ĐIỂM NGHẼN (BOTTLENECK). {check['warning']}")
    else:
        lines.append("- KẾT LUẬN TƯƠNG THÍCH: TƯƠNG THÍCH (PHÙ HỢP)")
        
    return "\n".join(lines) + "\n"
