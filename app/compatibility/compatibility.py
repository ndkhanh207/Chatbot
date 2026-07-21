# compat.py
"""
Orchestrator Module: Kết nối các module Logic, Intent, và Format.
Giữ nguyên giao diện API để không ảnh hưởng đến các module gọi từ ngoài (chat_handler).
"""

from app.catalog import ProductQuery, ShopCatalog, resolve_component
from app.constants import CATEGORY_MAP, CPU_TERMS, GPU_TERMS, MAIN_TERMS

# --- Import & Expose các thành phần từ các module con ---
from app.compatibility.compat_logic import (
    check_cpu_main_compat, check_gpu_main_compat,
    find_compatible_build,
)
from app.core.intent.master_intent import MasterIntentSchema
from app.utils.format import get_field, format_currency_vietnam

__all__ = [
    "build_compatibility_context", "build_suggestion_context",
    "resolve_component",
    "CPU_TERMS", "GPU_TERMS", "MAIN_TERMS",
]



# ──────────────────────────────────────────────
# Tích hợp với chat_handler
# ──────────────────────────────────────────────
def build_compatibility_context(intent: MasterIntentSchema, catalog: ShopCatalog) -> str:
    """Return catalog facts and exact comparisons; the model owns the wording."""
    cpu  = resolve_component(intent.cpu,       "CPU",       catalog) if intent.cpu else None
    main = resolve_component(intent.mainboard, "MAINBOARD", catalog) if intent.mainboard else None
    gpu  = resolve_component(intent.gpu,       "GPU",       catalog) if intent.gpu else None

    cpu_main = check_cpu_main_compat(cpu, main) if cpu and main else None
    gpu_main = check_gpu_main_compat(gpu, main) if gpu and main else None
    if cpu_main and cpu_main["status"] == "incompatible":
        overall = "incompatible"
    elif cpu_main or gpu_main:
        statuses = [check["status"] for check in (cpu_main, gpu_main) if check]
        overall = "compatible" if all(status == "compatible" for status in statuses) else "unknown"
    elif cpu and gpu:
        overall = "not_directly_checkable"
    else:
        overall = "unknown"

    def field(item: dict | None, *keys):
        return get_field(item, *keys, default=None) if item else None

    facts = {
        "OVERALL_STATUS": overall,
        "CPU_MODEL": field(cpu, "tên", "name"),
        "CPU_SOCKET": cpu_main.get("cpu_socket") if cpu_main else field(cpu, "socket", "socket_type"),
        "MAINBOARD_MODEL": field(main, "tên", "name"),
        "MAINBOARD_SOCKET": cpu_main.get("mainboard_socket") if cpu_main else field(main, "socket", "socket_type"),
        "SOCKET_MATCH": cpu_main.get("socket_match") if cpu_main else None,
        "GPU_MODEL": field(gpu, "tên", "name"),
        "GPU_MAIN_STATUS": gpu_main.get("status") if gpu_main else None,
        "GPU_PCIE_GEN": gpu_main.get("gpu_pcie_gen") if gpu_main else None,
        "MAINBOARD_PCIE_GEN": gpu_main.get("main_pcie_gen") if gpu_main else None,
        "BANDWIDTH_LIMITED": gpu_main.get("bandwidth_limited") if gpu_main else None,
    }
    render = lambda value: "null" if value is None else str(value).lower() if isinstance(value, bool) else str(value)
    return "[CATALOG_COMPATIBILITY_FACTS]\n" + "\n".join(
        f"- {key}: {render(value)}" for key, value in facts.items()
    )


def build_suggestion_context(
    intent: MasterIntentSchema,
    catalog: ShopCatalog,
    query_text: str = "",
    top_k: int = 5,
) -> str:
    """Gợi ý build dựa trên ĐÚNG 1 linh kiện đã có (intent.intent == 'suggestion')."""
    candidates = [("cpu", intent.cpu), ("mainboard", intent.mainboard), ("gpu", intent.gpu)]
    owned = [(t, n) for t, n in candidates if n and n.strip().lower() != "none"]
    if len(owned) != 1:
        return ""  # LLM trả nhiều/không linh kiện nào — không đủ rõ để gợi ý

    have_type, have_name = owned[0]
    
    # Bắt lỗi logic: Không thể ghép 2 linh kiện cùng loại (VD: Mainboard + Mainboard)
    if intent.category and intent.category.strip().lower() == have_type:
        type_display = {"cpu": "CPU", "mainboard": "Mainboard", "gpu": "Card màn hình"}.get(have_type, have_type.capitalize())
        return (
            f"[LỖI LOGIC TỪ NGƯỜI DÙNG]\n"
            f"Khách hàng đang yêu cầu tìm '{type_display}' để lắp chung với '{have_name}' (cũng là {type_display}).\n"
            f"=> Điều này là vô lý vì một bộ PC thông thường chỉ sử dụng 1 {type_display}.\n"
            f"Nhiệm vụ: Hãy từ chối khéo léo và giải thích rằng không thể lắp 2 {type_display} cùng nhau."
        )

    # Bắt lỗi Out of Scope: Yêu cầu tìm linh kiện ngoài danh mục hỗ trợ (RAM, SSD, Nguồn...)
    supported_categories = ["cpu", "mainboard", "gpu", "vga", "none"]
    if intent.category and intent.category.strip().lower() not in supported_categories:
        cat_name = intent.category.strip()
        return (
            f"[THÔNG BÁO TỪ HỆ THỐNG]\n"
            f"Khách hàng đang yêu cầu tìm linh kiện loại '{cat_name}'.\n"
            f"Hiện tại, hệ thống kiểm tra tương thích tự động CHỈ HỖ TRỢ các linh kiện: CPU, Mainboard, và VGA (Card màn hình).\n"
            f"Nhiệm vụ: Hãy lịch sự thông báo cho khách rằng tính năng gợi ý/kiểm tra tương thích cho '{cat_name}' chưa được hỗ trợ và đang trong quá trình cập nhật."
        )
    have_item = resolve_component(have_name, CATEGORY_MAP[have_type], catalog)
    if not have_item:
        return (
            f"[CẢNH BÁO TỪ HỆ THỐNG]\n"
            f"Khách cần tìm linh kiện ghép với '{have_name}', nhưng kho dữ liệu của cửa hàng "
            f"KHÔNG CÓ sản phẩm '{have_name}' này để trích xuất thông số tương thích.\n"
            f"=> Do đó không thể lọc tự động linh kiện tương thích.\n"
            f"Nhiệm vụ: Báo rõ cho khách biết hệ thống thiếu '{have_name}' nên chưa thể gợi ý chính xác."
        )

    inventory = []
    for category in ("CPU", "MAINBOARD", "GPU"):
        inventory.extend(
            product.as_legacy_dict()
            for product in catalog.search_products(
                ProductQuery(text=query_text, category=category, limit=1000)
            )
        )
    build = find_compatible_build(have_type, have_item, inventory, top_k=top_k)
    have_display_name = get_field(have_item, "tên", "name", default="")
    lines = [f"[GỢI Ý LINH KIỆN TƯƠNG THÍCH VỚI '{have_display_name}']"]

    for key, label in (("mainboards", "Mainboard"), ("cpus", "CPU"), ("gpus", "GPU")):
        items = build.get(key)
        if not items:
            continue
        lines.append(f"\n{label} phù hợp:")
        for entry in items[:top_k]:
            name = get_field(entry["item"], "tên", "name", default="")
            price_raw = get_field(entry["item"], "giá", "price", default=0)
            try:
                price_str = format_currency_vietnam(price_raw)
            except Exception:
                price_str = str(price_raw)
            line = f"  • {name} | {price_str} VNĐ"
            if entry["compat"].get("bandwidth_limited"):
                line += " (PCIe chạy theo thế hệ của mainboard)"
            lines.append(line)

    if len(lines) == 1:
        return (
            f"[KẾT QUẢ TÌM KIẾM]\n"
            f"Đã xác định '{have_display_name}' có thông số hợp lệ.\n"
            f"NHƯNG hiện tại cửa hàng KHÔNG CÓ linh kiện nào đáp ứng đủ điều kiện vật lý (ví dụ: cạn kho mainboard đúng socket).\n"
            f"Nhiệm vụ: Thông báo cửa hàng đang tạm hết linh kiện phù hợp với món đồ này."
        )

    return "\n".join(lines) + "\n"
