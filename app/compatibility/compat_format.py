def format_compatibility_reply(report: dict) -> str:
    """Minimal factual fallback used only when generation fails validation."""
    status = report["overall_status"]
    models = report.get("component_models", {})
    cpu = models.get("cpu")
    main = models.get("mainboard")
    gpu = models.get("gpu")
    names = " + ".join(name for name in (cpu, main, gpu) if name)
    cpu_main = report.get("cpu_main_check") or {}
    gpu_main = report.get("gpu_main_check") or {}

    if status == "incompatible":
        cpu_socket = cpu_main.get("cpu_socket") or "không rõ"
        main_socket = cpu_main.get("mainboard_socket") or "không rõ"
        return (
            f"Dạ, {names} không tương thích. Lý do: CPU dùng socket {cpu_socket}, "
            f"mainboard dùng socket {main_socket}, nên không lắp được với nhau."
        )
    if status == "compatible":
        details = []
        socket = cpu_main.get("cpu_socket")
        if socket:
            details.append(f"CPU và mainboard cùng socket {socket}")
        if gpu_main.get("status") == "compatible":
            details.append("GPU và mainboard có giao tiếp PCIe")
        if gpu_main.get("bandwidth_limited"):
            details.append(
                f"băng thông theo PCIe {gpu_main.get('main_pcie_gen')} của mainboard"
            )
        reason = "; ".join(details) or "các dữ liệu vật lý trong catalog phù hợp"
        return f"Dạ, {names} tương thích. Lý do: {reason}."
    if status == "not_directly_checkable":
        return (
            f"Dạ, catalog không có ràng buộc tương thích vật lý trực tiếp giữa {names}. "
            "Chưa đủ dữ liệu mainboard, nguồn, case và hiệu năng thực tế để kết luận thêm."
        )
    return f"Dạ, chưa đủ dữ liệu trong catalog để xác nhận độ tương thích của {names or 'các linh kiện này'}."
