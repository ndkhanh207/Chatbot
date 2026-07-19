
from __future__ import annotations

from typing import Any

from app.catalog import BuildRecord
from app.pc_builder.context import PcBuildContext
from app.pc_builder.policy import PendingQuestion


ROLE_MAP = {
    "human": "user",
    "user": "user",
    "ai": "assistant",
    "assistant": "assistant",
    "system": "system",
}


def format_vnd(value: int | float | None) -> str:
    """
    Hiển thị giá VNĐ chính xác.

    Ví dụ:
    25_250_500 -> "25.250.500 ₫"
    """
    if value is None:
        return "Không có dữ liệu"

    try:
        amount = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return "Không có dữ liệu"

    return f"{amount:,}".replace(",", ".") + " ₫"


def format_approx_million(value: int | float | None) -> str:
    """
    Hiển thị giá xấp xỉ theo triệu đồng.

    Chỉ nên dùng trong câu giải thích hoặc câu hỏi làm rõ,
    không dùng làm giá chính thức của cấu hình.

    Ví dụ:
    25_250_500 -> "~25,3 triệu"
    """
    if value is None:
        return "Không có dữ liệu"

    try:
        millions = round(float(value) / 1_000_000, 1)
    except (TypeError, ValueError, OverflowError):
        return "Không có dữ liệu"

    if millions.is_integer():
        return f"~{int(millions)} triệu"

    value_text = str(millions).replace(".", ",")
    return f"~{value_text} triệu"


def _is_integrated_gpu(build: BuildRecord) -> bool:
    """
    Xác định GPU tích hợp.

    Ưu tiên field rõ ràng từ catalog. Chỉ fallback sang price == 0
    khi dữ liệu hiện tại chưa có field chuyên biệt.
    """
    explicit_flag = build.attributes.get("GPU_Is_Integrated")

    if isinstance(explicit_flag, bool):
        return explicit_flag

    if isinstance(explicit_flag, str):
        normalized = explicit_flag.strip().casefold()

        if normalized in {"true", "1", "yes", "co", "có"}:
            return True

        if normalized in {"false", "0", "no", "khong", "không"}:
            return False

    gpu = build.components.get("gpu")

    if gpu is None:
        return False

    model = gpu.model.casefold()

    integrated_keywords = (
        "integrated",
        "igpu",
        "đồ họa tích hợp",
        "do hoa tich hop",
    )

    return gpu.price == 0 and any(
        keyword in model
        for keyword in integrated_keywords
    )


def format_build_context(build: BuildRecord) -> str:
    """
    Render block dữ liệu chính thức từ BuildRecord.

    Hàm này không gọi LLM và không tự tạo giá hoặc linh kiện.
    """
    cpu = build.components.get("cpu")
    gpu = build.components.get("gpu")
    mainboard = build.components.get("mainboard")

    missing_components = [
        category
        for category, component in {
            "CPU": cpu,
            "GPU": gpu,
            "Mainboard": mainboard,
        }.items()
        if component is None
    ]

    if missing_components:
        missing_text = ", ".join(missing_components)

        raise ValueError(
            f"Build '{build.build_id}' thiếu linh kiện: "
            f"{missing_text}"
        )
        
    assert cpu is not None
    assert gpu is not None
    assert mainboard is not None

    try:
        gpu_quantity = max(
            1,
            int(str(
                build.attributes.get(
                    "GPU_Quantity",
                    1,
                )
                or 1
            )),
        )
    except (TypeError, ValueError):
        gpu_quantity = 1

    lines = [
        f"- Mã bộ: {build.build_id}",
        f"- CPU: {cpu.model} | Giá: {format_vnd(cpu.price)}",
    ]

    if _is_integrated_gpu(build):
        lines.append(
            f"- GPU: {gpu.model} | Tích hợp trên CPU"
        )
    elif gpu_quantity > 1:
        gpu_total = gpu.price * gpu_quantity

        lines.append(
            f"- GPU: {gpu_quantity} × {gpu.model}"
            f" | Giá mỗi GPU: {format_vnd(gpu.price)}"
            f" | Tổng GPU: {format_vnd(gpu_total)}"
        )
    else:
        lines.append(
            f"- GPU: {gpu.model}"
            f" | Giá: {format_vnd(gpu.price)}"
        )

    lines.extend(
        [
            (
                f"- Mainboard: {mainboard.model}"
                f" | Giá: {format_vnd(mainboard.price)}"
            ),
            (
                f"- Phí lắp ráp: "
                f"{format_vnd(build.assembly_fee)}"
            ),
            (
                f"- Tổng cộng: "
                f"{format_vnd(build.total_price)}"
            ),
        ]
    )

    if build.detailed_purpose.strip():
        lines.append(
            f"- Phù hợp cho: "
            f"{build.detailed_purpose.strip()}"
        )

    if build.notes.strip():
        lines.append(
            f"- Lưu ý: {build.notes.strip()}"
        )

    return "\n".join(lines)


def interpretation_failure_reply(
    ctx: PcBuildContext,
) -> str:
    if ctx.pending_question == PendingQuestion.BUDGET:
        return (
            "Em chưa nhận diện được ngân sách. "
            "Bạn nhập một mức cụ thể, ví dụ 20 triệu nhé?"
        )
    if ctx.pending_question == PendingQuestion.PURPOSE:
        return (
            "Em chưa nhận diện được mục đích sử dụng. "
            "Bạn dùng máy chủ yếu để chơi game, làm việc "
            "hay xử lý đồ họa?"
        )
    if ctx.pending_question == PendingQuestion.BUDGET_SCOPE:
        return (
            "Bạn xác nhận ngân sách vừa nói là tổng cho tất cả "
            "các bộ hay ngân sách của mỗi bộ nhé?"
        )
    if ctx.pending_question == PendingQuestion.GENERAL:
        return (
            "Bạn cho em biết ngân sách và mục đích sử dụng "
            "chính của bộ PC nhé?"
        )
    if ctx.build_id:
        return (
            "Em chưa xác định được phần bạn muốn thay đổi. "
            "Bạn muốn đổi CPU, GPU, mainboard hay ngân sách?"
        )
    return (
        "Em chưa hiểu rõ yêu cầu ráp PC. "
        "Bạn mô tả lại ngân sách và nhu cầu chính nhé?"
    )


def render_selected_build_reply(
    canonical_block: str,
    explanation: str | None,
) -> str:
    """
    Ghép phần giải thích của LLM với block dữ liệu tất định.

    canonical_block luôn là phần dữ liệu chính thức.
    """
    canonical_block = canonical_block.strip()

    if not canonical_block:
        raise ValueError(
            "canonical_block không được để trống"
        )

    parts: list[str] = []

    if explanation and explanation.strip():
        parts.append(
            "Lý do lựa chọn:\n"
            + explanation.strip()
        )

    parts.append(
        "Thông tin cấu hình:\n"
        + canonical_block
    )

    return "\n\n".join(parts)


def format_merge_conflict_error(
    error_message: str,
) -> str:
    cleaned = error_message.strip().rstrip(".!?")

    if not cleaned:
        return (
            "Yêu cầu hiện tại có thông tin mâu thuẫn. "
            "Bạn nói rõ lại giúp em nhé?"
        )

    return (
        f"Yêu cầu có mâu thuẫn: {cleaned}. "
        "Bạn nói rõ lại giúp em nhé?"
    )


def _extract_message(
    message: Any,
) -> tuple[str, str]:
    if isinstance(message, dict):
        raw_role = str(
            message.get("role", "unknown")
        )
        content = str(
            message.get("content", "")
        )
    else:
        raw_role = str(
            getattr(message, "type", "unknown")
        )
        content = str(
            getattr(message, "content", "")
        )

    role = ROLE_MAP.get(
        raw_role.casefold(),
        "unknown",
    )
    return role, content.strip()
def format_chat_history(
    messages: list,
    limit: int,
) -> str:
    """
    Chuyển lịch sử chat thành văn bản ngắn cho bước Interpretation.
    """
    if limit <= 0 or not messages:
        return ""

    formatted: list[str] = []

    for message in messages[-limit:]:
        role, content = _extract_message(message)

        if not content:
            continue

        formatted.append(
            f"{role}: {content}"
        )

    return "\n".join(formatted)
