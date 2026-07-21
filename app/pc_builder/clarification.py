from __future__ import annotations

from app.pc_builder.context import PcBuildContext
from app.pc_builder.policy import PendingQuestion


def _has_workload_direction(
    ctx: PcBuildContext,
) -> bool:
    """
    Người dùng đã đưa ra yêu cầu về linh kiện (CPU, GPU...) đủ rõ
    để định hình sức mạnh hoặc mục đích của bộ máy.
    """
    return any(
        (
            ctx.required_components,
            ctx.preferred_components,
        )
    )



def clear_satisfied_pending_question(
    ctx: PcBuildContext,
) -> None:
    """
    Xóa pending_question khi câu trả lời mới đã cung cấp
    đủ dữ liệu được yêu cầu.
    """
    pending = ctx.pending_question
    has_workload_direction = _has_workload_direction(ctx)

    if pending in (PendingQuestion.BUDGET, PendingQuestion.BUDGET_SCOPE):
        if ctx.budget is not None:
            ctx.pending_question = None

    elif pending == PendingQuestion.PURPOSE:
        if ctx.purpose or has_workload_direction:
            ctx.pending_question = None

    elif pending == PendingQuestion.GENERAL:
        has_budget = ctx.budget is not None
        has_usage_direction = bool(
            ctx.purpose or has_workload_direction
        )

        if has_budget and has_usage_direction:
            ctx.pending_question = None


def evaluate_request_completeness(
    ctx: PcBuildContext,
) -> PendingQuestion | None:
    """
    Kiểm tra state hiện tại đã đủ dữ liệu để tìm PC hay chưa.

    Hàm này không đọc câu người dùng và không gọi LLM.
    """
    if ctx.pending_question is not None:
        return ctx.pending_question

    has_budget = ctx.budget is not None
    has_purpose = bool(
        ctx.purpose and ctx.purpose.strip()
    )
    has_workload_direction = _has_workload_direction(ctx)

    # Không có bất kỳ thông tin quan trọng nào.
    if not has_budget and not has_purpose and not has_workload_direction:
        return PendingQuestion.GENERAL

    # Đã biết mục đích hoặc linh kiện nhưng chưa có ngân sách.
    if not has_budget:
        return PendingQuestion.BUDGET

    # Đã có ngân sách nhưng chưa biết mục đích và cũng không có
    # định hướng linh kiện (workload).
    if not has_purpose and not has_workload_direction:
        return PendingQuestion.PURPOSE

    return None
