import re

def _value(context: str, key: str) -> str | None:
    match = re.search(rf"^- {re.escape(key)}: (.+)$", context, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    return None if value == "null" else value


def format_compatibility_reply(context: str) -> str:
    """Minimal factual fallback used only when generawtion fails validation."""
    status = _value(context, "OVERALL_STATUS")
    cpu = _value(context, "CPU_MODEL")
    main = _value(context, "MAINBOARD_MODEL")
    gpu = _value(context, "GPU_MODEL")
    names = " + ".join(name for name in (cpu, main, gpu) if name)

    if status == "incompatible":
        cpu_socket = _value(context, "CPU_SOCKET") or "không rõ"
        main_socket = _value(context, "MAINBOARD_SOCKET") or "không rõ"
        return (
            f"Dạ, {names} không tương thích. Lý do: CPU dùng socket {cpu_socket}, "
            f"mainboard dùng socket {main_socket}, nên không lắp được với nhau."
        )
    if status == "compatible":
        details = []
        socket = _value(context, "CPU_SOCKET")
        if socket:
            details.append(f"CPU và mainboard cùng socket {socket}")
        if _value(context, "GPU_MAIN_STATUS") == "compatible":
            details.append("GPU và mainboard có giao tiếp PCIe")
        if _value(context, "BANDWIDTH_LIMITED") == "true":
            details.append(
                f"băng thông theo PCIe {_value(context, 'MAINBOARD_PCIE_GEN')} của mainboard"
            )
        reason = "; ".join(details) or "các dữ liệu vật lý trong catalog phù hợp"
        return f"Dạ, {names} tương thích. Lý do: {reason}."
    if status == "not_directly_checkable":
        return (
            f"Dạ, catalog không có ràng buộc tương thích vật lý trực tiếp cho {names}. "
            "Cần thêm mainboard và dữ liệu hiệu năng thực tế để đánh giá sâu hơn."
        )
    return f"Dạ, chưa đủ dữ liệu trong catalog để xác nhận độ tương thích của {names or 'các linh kiện này'}."
