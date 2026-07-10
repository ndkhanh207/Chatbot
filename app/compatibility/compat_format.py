import re

from app.price.pricing_util import format_currency_vietnam, calculate_total_price
from app.compatibility.compat_logic import _get_field


def _find_context_line(lines: list[str], marker: str) -> str:
    return next((line for line in lines if marker in line), "")


def _line_value(line: str) -> str:
    return line.split(":", 1)[1].strip() if ":" in line else line.strip("- ").strip()


def _plain_compat_reason(text: str) -> str:
    reason = _line_value(text)
    socket_match = re.search(r"CPU dùng ([^,.]+), mainboard dùng ([^,.]+)", reason, re.IGNORECASE)
    if socket_match:
        return (
            "CPU và mainboard khác chuẩn chân cắm: "
            f"CPU dùng {socket_match.group(1)}, mainboard dùng {socket_match.group(2)}, "
            "nên không lắp được với nhau."
        )
    return (
        reason
        .replace("Hoàn toàn TƯƠNG THÍCH (PHÙ HỢP): ", "")
        .replace("KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP): ", "")
        .replace("CPU và GPU cân bằng theo tier", "CPU và GPU cân bằng")
    )


def format_compatibility_reply(context: str) -> str:
    if not context:
        return "Dạ em chưa tìm thấy thông tin tương thích phù hợp ạ."
    lines = [
        line for line in context.splitlines()
        if line.strip() and not line.startswith("[KIỂM TRA")
    ]
    overall = _find_context_line(lines, "KẾT LUẬN")
    incompatible = "KHÔNG TƯƠNG THÍCH" in overall

    cpu_main = _find_context_line(lines, "CHI TIẾT CPU + Mainboard")
    gpu_main = _find_context_line(lines, "CHI TIẾT GPU + Mainboard") or _find_context_line(lines, "CẢNH BÁO BĂNG THÔNG")
    cpu_gpu = _find_context_line(lines, "CHI TIẾT CPU + GPU") or _find_context_line(lines, "CẢNH BÁO QUAN TRỌNG CPU + GPU")

    if not any((cpu_main, gpu_main, cpu_gpu)):
        return "Dạ, đây là kết quả kiểm tra tương thích:\n\n" + "\n".join(lines)

    reply = ["Dạ, combo này không tương thích." if incompatible else "Dạ, combo này tương thích."]
    if cpu_main:
        label = "Lý do chính" if incompatible else "Lý do"
        reply.append(f"{label}: {_plain_compat_reason(cpu_main)}")
    if gpu_main:
        reply.append(f"- GPU + Mainboard: {_plain_compat_reason(gpu_main)}")
    if cpu_gpu:
        reply.append(f"- CPU + GPU: {_plain_compat_reason(cpu_gpu)}")

    if incompatible:
        reply.append("Nói ngắn gọn: chỉ cần CPU không lắp được mainboard thì cả combo này không dùng được.")

    return "\n\n".join([reply[0], "\n".join(reply[1:])])


def _fmt_component_combo(cpu: dict, main: dict, gpu: dict, cpu_main_check: dict, gpu_main_check: dict, cpu_gpu_check: dict) -> str:
    cpu_price = _get_field(cpu, 'giá', 'price', default=None)
    main_price = _get_field(main, 'giá', 'price', default=None)
    gpu_price = _get_field(gpu, 'giá', 'price', default=None)
    cpu_price_str = f" | Giá: {format_currency_vietnam(cpu_price)} VNĐ" if cpu_price else ""
    main_price_str = f" | Giá: {format_currency_vietnam(main_price)} VNĐ" if main_price else ""
    gpu_price_str = f" | Giá: {format_currency_vietnam(gpu_price)} VNĐ" if gpu_price else ""

    is_compatible = cpu_main_check["is_compatible"] and gpu_main_check["is_compatible"]
    verdict = "TƯƠNG THÍCH (PHÙ HỢP)" if is_compatible else "KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP)"

    lines = [
        "[KIỂM TRA TƯƠNG THÍCH COMBO 3 LINH KIỆN]",
        f"- CPU: '{_get_field(cpu, 'tên', 'name', default='')}'{cpu_price_str}",
        f"- Mainboard: '{_get_field(main, 'tên', 'name', default='')}' (Chipset: {cpu_main_check.get('chipset') or 'không rõ'}, PCIe: {gpu_main_check.get('main_pcie_gen') or '?'}){main_price_str}",
        f"- GPU: '{_get_field(gpu, 'tên', 'name', default='')}' (PCIe: {gpu_main_check.get('gpu_pcie_gen') or '?'}){gpu_price_str}",
    ]

    total_str = calculate_total_price(cpu_price, main_price, gpu_price)
    if total_str:
        lines.append(total_str)

    lines.extend([
        f"- KẾT LUẬN TỔNG THỂ: {verdict}",
        f"- CPU + Mainboard: {'TƯƠNG THÍCH (PHÙ HỢP)' if cpu_main_check['is_compatible'] else 'KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP)'}",
    ])
    lines.extend(f"- CHI TIẾT CPU + Mainboard: {reason}" for reason in cpu_main_check["reasons"])

    lines.append("- GPU + Mainboard: TƯƠNG THÍCH (PHÙ HỢP)")
    if gpu_main_check.get("warning"):
        lines.append(f"- CẢNH BÁO BĂNG THÔNG GPU + Mainboard: {gpu_main_check['warning']}")
    else:
        lines.append("- CHI TIẾT GPU + Mainboard: GPU và mainboard dùng chuẩn PCIe tương thích.")

    lines.append("- CPU + GPU: TƯƠNG THÍCH (PHÙ HỢP)")
    if cpu_gpu_check.get("warning"):
        lines.append(f"- CẢNH BÁO QUAN TRỌNG CPU + GPU: Cấu hình này CÓ ĐIỂM NGHẼN (BOTTLENECK). {cpu_gpu_check['warning']}")
    else:
        lines.append("- CHI TIẾT CPU + GPU: CPU và GPU cân bằng theo tier, không thấy cảnh báo nghẽn rõ rệt.")

    return "\n".join(lines) + "\n"

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
