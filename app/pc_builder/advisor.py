# pc_build_advisor.py
"""
Module tư vấn bộ PC trọn gói (CPU + GPU + Mainboard).
Tìm kiếm bộ PC phù hợp nhất dựa trên ngân sách và mục đích sử dụng.
Đóng vai trò Facade: Export lại các hàm từ module con để không làm gãy code cũ.
"""

import pandas as pd

# Re-export các hằng số
from .constants import (
    BUILD_PC_TRIGGERS, PURPOSE_KEYWORD_MAP, CPU_BRAND_MAP, GPU_BRAND_MAP
)

# Re-export các hàm extraction
from .extractor import (
    detect_build_pc_intent, extract_budget, extract_quantity,
    extract_brand_filter, extract_component_filter, extract_explicit_build_id
)

# Re-export các hàm formatter
from .formatter import format_approx_million, format_build_context

__all__ = [
    # constants
    "BUILD_PC_TRIGGERS", "PURPOSE_KEYWORD_MAP", "CPU_BRAND_MAP", "GPU_BRAND_MAP",
    # extractor
    "detect_build_pc_intent", "extract_budget", "extract_quantity",
    "extract_brand_filter", "extract_component_filter", "extract_explicit_build_id",
    # formatter
    "format_approx_million", "format_build_context",
    # advisor (self)
    "find_best_build"
]

# ──────────────────────────────────────────────
# Tính điểm phù hợp mục đích
# ──────────────────────────────────────────────
def _score_purpose(build_notes: str, user_msg_lower: str) -> float:
    """
    Cho điểm bộ PC theo độ phù hợp với mục đích của user.
    Điểm cao hơn = phù hợp hơn.
    """
    notes_lower = build_notes.lower()
    score = 0.0

    for purpose_key, synonyms in PURPOSE_KEYWORD_MAP.items():
        # Kiểm tra xem user có nhắc đến mục đích này không
        user_mentions_purpose = (
            purpose_key in user_msg_lower
            or any(s in user_msg_lower for s in synonyms)
        )
        if not user_mentions_purpose:
            continue

        # Nếu user có nhắc → kiểm tra Build_Notes có match không
        for synonym in synonyms:
            if synonym in notes_lower:
                score += 2.0

        # Bonus nếu purpose_key chính xuất hiện trong notes
        if purpose_key in notes_lower:
            score += 1.0

    return score

# ──────────────────────────────────────────────
# Hàm tìm bộ PC tốt nhất
# ──────────────────────────────────────────────
def find_best_build(
    budget: int,
    user_message: str,
    build_df: pd.DataFrame,
    exclude_builds: list = None,
    brand_filter: dict = None,
    component_filter: dict = None,
    find_cheapest: bool = False,
) -> dict | None:
    """
    Tìm bộ PC phù hợp nhất trong DataFrame.
    """
    if build_df is None or build_df.empty:
        return None

    filtered = build_df.copy()

    # Filter theo component model cụ thể trước
    if component_filter:
        gpu_model_req = component_filter.get('gpu_model')
        cpu_model_req = component_filter.get('cpu_model')
        if gpu_model_req:
            mask = filtered['GPU_Model'].str.lower().str.contains(gpu_model_req, na=False)
            filtered = filtered[mask]
        if cpu_model_req:
            mask = filtered['CPU_Model'].str.lower().str.contains(cpu_model_req, na=False)
            filtered = filtered[mask]
        # Nếu sau filter không còn row nào → báo không có
        if filtered.empty:
            return None

    # Filter theo brand CPU/GPU
    if brand_filter:
        cpu_brand = brand_filter.get('cpu_brand')
        gpu_brand = brand_filter.get('gpu_brand')
        any_brand = brand_filter.get('any_brand')

        if cpu_brand:
            filtered = filtered[filtered['CPU_Brand'].str.lower() == cpu_brand.lower()]
        if gpu_brand:
            filtered = filtered[filtered['GPU_Brand'].str.lower() == gpu_brand.lower()]
        if any_brand:
            filtered = filtered[
                (filtered['CPU_Brand'].str.lower() == any_brand.lower()) |
                (filtered['GPU_Brand'].str.lower() == any_brand.lower()) |
                (filtered['Motherboard_Model'].str.lower().str.contains(any_brand.lower(), na=False))
            ]
        
        if filtered.empty:
            return None

    # Nếu tìm rẻ nhất → không filter theo budget
    if find_cheapest:
        if filtered.empty:
            return None
        best_row = filtered.sort_values('Total_Price', ascending=True).iloc[0]
        result = best_row.to_dict()
        return result

    # Lọc theo khoảng ngân sách: 75% → 115% của budget user
    budget_min = budget * 0.75
    budget_max = budget * 1.15

    filtered = filtered[
        (filtered['Total_Price'] >= budget_min) &
        (filtered['Total_Price'] <= budget_max)
    ]

    # Loại bỏ các bộ PC đã gợi ý trước đó (nếu có)
    if exclude_builds and not filtered.empty:
        filtered = filtered[~filtered['BuildID'].isin(exclude_builds)]

    if filtered.empty:
        return None

    user_msg_lower = user_message.lower()

    # Tính điểm mục đích
    filtered.loc[:, '_purpose_score'] = filtered['Build_Notes'].fillna('').apply(
        lambda notes: _score_purpose(notes, user_msg_lower)
    )

    # Tính điểm gần budget (càng gần budget gốc càng tốt)
    safe_budget = max(budget, 1)
    filtered.loc[:, '_budget_score'] = 1.0 - (
        (filtered['Total_Price'] - budget).abs() / safe_budget
    ).clip(upper=1.0)

    # Điểm tổng hợp: mục đích ưu tiên cao hơn, budget là tiebreaker
    filtered.loc[:, '_combined_score'] = (
        filtered['_purpose_score'] * 2.0 +
        filtered['_budget_score'] * 1.0
    )

    best_row = filtered.sort_values('_combined_score', ascending=False).iloc[0]

    # Dọn dẹp cột tạm trước khi trả về
    result = best_row.to_dict()
    for col in ['_purpose_score', '_budget_score', '_combined_score']:
        result.pop(col, None)

    return result