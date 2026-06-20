# compat.py
"""
Orchestrator Module: Kết nối các module Logic, Intent, và Format.
Giữ nguyên giao diện API để không ảnh hưởng đến các module gọi từ ngoài (chat_handler).
"""

from typing import Optional

from app.search_engine import hybrid_search

# --- Import & Expose các thành phần từ các module con ---
from app.compact.compat_logic import (
    CATEGORY_MAP, _get_field, check_cpu_main_compat, check_gpu_main_compat, check_cpu_gpu_compat,
    is_compatibility_query, find_compatible_build,
    CPU_TERMS, GPU_TERMS, MAIN_TERMS  # Expose cho chat_handler
)
from app.compact.compat_format import _fmt_cpu_main, _fmt_gpu_main, _fmt_cpu_gpu
from app.compact.compat_intent import parse_compat_intent, PCIntentSchema
from app.price.pricing import format_currency_vietnam

__all__ = [
    "build_compatibility_context", "build_suggestion_context",
    "is_compatibility_query", "parse_compat_intent", "PCIntentSchema",
    "CPU_TERMS", "GPU_TERMS", "MAIN_TERMS",
]


def _resolve_item(name: str, category: str, knowledge_base, vector_store) -> Optional[dict]:
    """Tra cứu 1 linh kiện trong DB từ tên đã bóc tách. None nếu 'none'/rỗng
    hoặc hybrid_search không tìm thấy match nào."""
    if not name or name.strip().lower() == "none":
        return None
    normalized_name = name.lower().replace("-", " ")
    results = hybrid_search(normalized_name, category, 1, knowledge_base, vector_store)
    return results[0] if results else None


# ──────────────────────────────────────────────
# Tích hợp với chat_handler
# ──────────────────────────────────────────────
def build_compatibility_context(intent: PCIntentSchema, knowledge_base, vector_store) -> str:
    """Check 1 cặp cụ thể, dựa trên tên linh kiện đã bóc tách bởi parse_compat_intent."""
    cpu  = _resolve_item(intent.cpu,       "CPU",       knowledge_base, vector_store)
    main = _resolve_item(intent.mainboard, "MAINBOARD", knowledge_base, vector_store)
    gpu  = _resolve_item(intent.gpu,       "GPU",       knowledge_base, vector_store)

    context = ""
    if cpu and main:
        context += _fmt_cpu_main(cpu, main, check_cpu_main_compat(cpu, main))
    if gpu and main:
        context += _fmt_gpu_main(gpu, main, check_gpu_main_compat(gpu, main))
    if cpu and gpu and not main:
        context += _fmt_cpu_gpu(cpu, gpu, check_cpu_gpu_compat(cpu, gpu))

    if not context:
        return (
            "[CẢNH BÁO TỪ HỆ THỐNG]\n"
            "Khách hỏi về độ tương thích nhưng kho dữ liệu hiện tại KHÔNG CÓ thông tin "
            "về một trong các linh kiện khách nhắc đến. Không thể trích xuất Socket/PCIe để kiểm tra.\n"
            "Nhiệm vụ: Lịch sự báo cho khách biết cửa hàng không có linh kiện này."
        )
    return context


def build_suggestion_context(intent: PCIntentSchema, knowledge_base, vector_store, top_k: int = 5) -> str:
    """Gợi ý build dựa trên ĐÚNG 1 linh kiện đã có (intent.intent == 'suggestion')."""
    candidates = [("cpu", intent.cpu), ("mainboard", intent.mainboard), ("gpu", intent.gpu)]
    owned = [(t, n) for t, n in candidates if n and n.strip().lower() != "none"]
    if len(owned) != 1:
        return ""  # LLM trả nhiều/không linh kiện nào — không đủ rõ để gợi ý

    have_type, have_name = owned[0]
    have_item = _resolve_item(have_name, CATEGORY_MAP[have_type], knowledge_base, vector_store)
    if not have_item:
        return (
            f"[CẢNH BÁO TỪ HỆ THỐNG]\n"
            f"Khách cần tìm linh kiện ghép với '{have_name}', nhưng kho dữ liệu của cửa hàng "
            f"KHÔNG CÓ sản phẩm '{have_name}' này để trích xuất thông số (như socket, tdp...).\n"
            f"=> Do đó không thể lọc tự động linh kiện tương thích.\n"
            f"Nhiệm vụ: Báo rõ cho khách biết hệ thống thiếu '{have_name}' nên chưa thể gợi ý chính xác."
        )

    build = find_compatible_build(have_type, have_item, knowledge_base, top_k=top_k)
    have_display_name = _get_field(have_item, "tên", "name", default="")
    lines = [f"[GỢI Ý LINH KIỆN TƯƠNG THÍCH VỚI '{have_display_name}']"]

    for key, label in (("mainboards", "Mainboard"), ("cpus", "CPU"), ("gpus", "GPU")):
        items = build.get(key)
        if not items:
            continue
        lines.append(f"\n{label} phù hợp:")
        for entry in items[:top_k]:
            name = _get_field(entry["item"], "tên", "name", default="")
            price_raw = _get_field(entry["item"], "giá", "price", default=0)
            try:
                price_str = format_currency_vietnam(price_raw)
            except Exception:
                price_str = str(price_raw)
            warn = entry["compat"].get("warning")
            line = f"  • {name} | {price_str} VNĐ"
            if warn:
                line += f" (⚠ {warn})"
            lines.append(line)

    if len(lines) == 1:
        return (
            f"[KẾT QUẢ TÌM KIẾM]\n"
            f"Đã xác định '{have_display_name}' có thông số hợp lệ.\n"
            f"NHƯNG hiện tại cửa hàng KHÔNG CÓ linh kiện nào đáp ứng đủ điều kiện vật lý (ví dụ: cạn kho mainboard đúng socket).\n"
            f"Nhiệm vụ: Thông báo cửa hàng đang tạm hết linh kiện phù hợp với món đồ này."
        )

    return "\n".join(lines) + "\n"