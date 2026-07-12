# pc_build_advisor.py
"""
Module tư vấn bộ PC trọn gói (CPU + GPU + Mainboard).
Tìm kiếm bộ PC phù hợp nhất dựa trên ngân sách và mục đích sử dụng.
Đóng vai trò Facade: Export lại các hàm từ module con để không làm gãy code cũ.
"""

import pandas as pd
from app.compatibility.compat_logic import parse_cpu_profile, parse_gpu_profile

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
# Tính điểm ưu tiên linh kiện (Priority Bias)
# ──────────────────────────────────────────────
def _apply_priority_bias(df: pd.DataFrame, priority_bias: dict) -> None:
    def get_cpu_tier(model_name: str) -> int:
        p = parse_cpu_profile(model_name)
        return p['tier_rank'] if p and 'tier_rank' in p else 1
        
    def get_gpu_tier(model_name: str) -> int:
        p = parse_gpu_profile(model_name)
        return p['tier_rank'] if p and 'tier_rank' in p else 1

    df.loc[:, '_cpu_tier'] = df['CPU_Model'].apply(get_cpu_tier)
    df.loc[:, '_gpu_tier'] = df['GPU_Model'].apply(get_gpu_tier)
    
    # Thưởng điểm cho mục đích cụ thể
    if priority_bias.get('purpose_bias') == 'esport':
        df.loc[:, '_priority_score'] += df['_cpu_tier'] * 1.0
        mask = df['Build_Notes'].str.lower().str.contains('esport|moba|fps', na=False)
        df.loc[mask, '_priority_score'] += 2.0
        
    elif priority_bias.get('purpose_bias') == 'workstation':
        df.loc[:, '_priority_score'] += df['_cpu_tier'] * 2.0
        mask = df['Build_Notes'].str.lower().str.contains('render|máy trạm|workstation', na=False)
        df.loc[mask, '_priority_score'] += 2.0
        
    elif priority_bias.get('purpose_bias') == 'game_aaa':
        df.loc[:, '_priority_score'] += df['_gpu_tier'] * 2.0
        mask = df['Build_Notes'].str.lower().str.contains('4k|2k|aaa', na=False)
        df.loc[mask, '_priority_score'] += 2.0
    
    # Thưởng điểm cho bias linh kiện
    if priority_bias.get('gpu_heavy'):
        ratio = (df['Component_Price_GPU'] / df['Component_Price_CPU'].clip(lower=1)).clip(upper=5)
        df.loc[:, '_priority_score'] += (df['_gpu_tier'] * 2.0) + ratio
        
    elif priority_bias.get('cpu_heavy'):
        ratio = (df['Component_Price_CPU'] / df['Component_Price_GPU'].clip(lower=1)).clip(upper=5)
        df.loc[:, '_priority_score'] += (df['_cpu_tier'] * 2.0) + ratio

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
    budget: int | None,
    user_message: str,
    build_df: pd.DataFrame,
    exclude_builds: list = None,
    brand_filter: dict = None,
    component_filter: dict = None,
    priority_bias: dict = None,
    price_order: str | None = None,
) -> dict | None:
    """
    Tìm bộ PC phù hợp nhất dựa trên các tiêu chí lọc:
    1. Lọc theo linh kiện bắt buộc (CPU, GPU, Mainboard)
    2. Lọc theo thương hiệu (Brand)
    3. Loại bỏ các bộ máy đã gợi ý trước đó
    4. Kiểm tra giới hạn ngân sách (75% -> 115%)
    5. Chấm điểm các bộ máy hợp lệ để chọn ra bộ tốt nhất
    """
    if build_df is None or build_df.empty:
        return None

    df = build_df.copy()

    # 1. Lọc theo linh kiện bắt buộc
    if component_filter:
        if gpu := component_filter.get('gpu_model'):
            df = df[df['GPU_Model'].str.contains(gpu, case=False, na=False)]
        if cpu := component_filter.get('cpu_model'):
            df = df[df['CPU_Model'].str.contains(cpu, case=False, na=False)]
        if main := component_filter.get('mainboard'):
            df = df[df['Motherboard_Model'].str.contains(main, case=False, na=False)]

    if df.empty: 
        return None

    # 2. Lọc theo thương hiệu
    if brand_filter:
        if cb := brand_filter.get('cpu_brand'):
            df = df[df['CPU_Brand'].str.casefold() == cb.casefold()]
        if gb := brand_filter.get('gpu_brand'):
            df = df[df['GPU_Brand'].str.casefold() == gb.casefold()]
        if ab := brand_filter.get('any_brand'):
            ab = ab.casefold()
            df = df[
                (df['CPU_Brand'].str.casefold() == ab) |
                (df['GPU_Brand'].str.casefold() == ab) |
                (df['Motherboard_Model'].str.contains(ab, case=False, na=False))
            ]

    if df.empty: 
        return None

    # 3. Loại bỏ các bộ PC đã từng gợi ý
    if exclude_builds:
        df = df[~df['BuildID'].isin(exclude_builds)]
        if df.empty: 
            return None

    if price_order in {"asc", "desc"}:
        return df.sort_values('Total_Price', ascending=price_order == "asc").iloc[0].to_dict()

    # 4. Kiểm tra khoảng ngân sách an toàn (75% - 115%)
    budget_min = budget * 0.75
    budget_max = budget * 1.15
    df_budget = df[(df['Total_Price'] >= budget_min) & (df['Total_Price'] <= budget_max)].copy()

    if df_budget.empty:
        df_cheaper = df[df['Total_Price'] < budget_min].copy()
        if not df_cheaper.empty:
            df_budget = df_cheaper
        else:
            return {"out_of_budget": True, "min_price": df['Total_Price'].min()}

    # 5. Chấm điểm các bộ máy hợp lệ
    user_msg_lower = user_message.lower()
    
    # - Điểm mục đích (Purpose Score)
    df_budget.loc[:, '_purpose_score'] = df_budget['Build_Notes'].fillna('').apply(
        lambda notes: _score_purpose(notes, user_msg_lower)
    )

    # - Điểm sát ngân sách (Budget Score)
    safe_budget = max(budget, 1)
    df_budget.loc[:, '_budget_score'] = 1.0 - (
        (df_budget['Total_Price'] - budget).abs() / safe_budget
    ).clip(upper=1.0)
    
    # - Điểm ưu tiên linh kiện (Priority Score)
    df_budget.loc[:, '_priority_score'] = 0.0
    if priority_bias:
        _apply_priority_bias(df_budget, priority_bias)

    # 6. Tổng kết điểm và chọn bộ tốt nhất
    df_budget.loc[:, '_combined_score'] = (
        df_budget['_purpose_score'] * 2.0 +
        df_budget['_budget_score'] * 1.0 +
        df_budget['_priority_score'] * 1.5
    )

    best_row = df_budget.sort_values('_combined_score', ascending=False).iloc[0]

    # Dọn dẹp cột tạm trước khi trả về
    result = best_row.to_dict()
    for col in ['_purpose_score', '_budget_score', '_priority_score', '_cpu_tier', '_gpu_tier', '_combined_score']:
        result.pop(col, None)

    return result
