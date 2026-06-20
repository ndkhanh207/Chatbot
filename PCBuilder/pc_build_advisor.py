# pc_build_advisor.py
"""
Module tư vấn bộ PC trọn gói (CPU + GPU + Mainboard).
Tìm kiếm bộ PC phù hợp nhất dựa trên ngân sách và mục đích sử dụng
từ file data/Pc_build_data_cleaned.csv.
"""

import re
import pandas as pd
from pathlib import Path

# ──────────────────────────────────────────────
# Từ khóa detect intent "build PC"
# ──────────────────────────────────────────────
BUILD_PC_TRIGGERS = [
    'build pc', 'build 1 bộ', 'build một bộ', 'build bo',
    'xây dựng pc', 'tư vấn bộ pc', 'tư vấn pc',
    'bộ pc', 'cấu hình pc', 'dựng pc', 'lắp pc',
    'trọn bộ', 'bộ máy tính', 'cấu hình máy',
    'máy tính tầm', 'pc tầm', 'máy tính dưới',
    'pc gaming', 'máy gaming', 'bộ khác', 'cấu hình khác'
]

# ──────────────────────────────────────────────
# Bảng ánh xạ mục đích → từ khóa trong Build_Notes
# ──────────────────────────────────────────────
PURPOSE_KEYWORD_MAP = {
    'game aaa': [
        'game aaa', 'triple aaa', 'chơi game aaa', '4k/2k',
        'chơi game 4k', 'game nặng', 'chơi game ở 4k',
    ],
    'game':    ['chơi game', 'game', 'esports', 'gaming', 'stream game'],
    'render':  ['render 3d', 'render', 'dựng phim', 'blender', 'maya'],
    'đồ họa': ['render 3d', 'dựng phim', 'đồ họa kỹ thuật', 'autodesk'],
    'lập trình': ['lập trình', 'máy ảo', 'data science', 'xử lý dữ liệu'],
    'văn phòng': ['văn phòng', 'word', 'excel', 'học tập', 'lướt web', 'cơ bản'],
    'ai':      ['deep learning', 'huấn luyện ai', 'ai'],
    'stream':  ['stream game', 'stream đa nền tảng'],
}

# ──────────────────────────────────────────────
# Intent detection
# ──────────────────────────────────────────────
def detect_build_pc_intent(msg: str) -> bool:
    """Trả về True nếu user đang hỏi về gợi ý bộ PC trọn bộ."""
    msg_lower = msg.lower()
    return any(trigger in msg_lower for trigger in BUILD_PC_TRIGGERS)


# ──────────────────────────────────────────────
# Trích xuất ngân sách từ câu hỏi
# ──────────────────────────────────────────────
def extract_budget(msg: str) -> int | None:
    """
    Trích xuất ngân sách (VNĐ) từ câu hỏi của user.
    Ví dụ: '30 triệu' → 30_000_000, '15tr' → 15_000_000
    """
    msg_lower = msg.lower().replace(',', '.').replace(' ', '')

    # Ưu tiên pattern có từ "triệu" hoặc "tr"
    patterns = [
        r'(\d+(?:\.\d+)?)\s*triệu',
        r'(\d+(?:\.\d+)?)\s*tr(?!\w)',       # "30tr" không khớp "trang"
        r'(\d+)\s*000\s*000',                  # "30 000 000"
        r'(\d{2,3})\s*(?:nghìn|k)\s*000',     # "30k000" hiếm gặp
    ]

    for pattern in patterns:
        match = re.search(pattern, msg_lower, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            return int(val * 1_000_000)

    return None


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
def find_best_build(budget: int, user_message: str, build_df: pd.DataFrame, exclude_builds: list = None) -> dict | None:
    """
    Tìm bộ PC phù hợp nhất trong DataFrame.

    Args:
        budget:       Ngân sách của user (VNĐ).
        user_message: Câu hỏi gốc của user (dùng để score mục đích).
        build_df:     DataFrame từ Pc_build_data_cleaned.csv.
        exclude_builds: List các BuildID cần loại trừ.

    Returns:
        dict chứa thông tin bộ PC, hoặc None nếu không tìm được.
    """
    if build_df is None or build_df.empty:
        return None

    # Lọc theo khoảng ngân sách: 75% → 115% của budget user
    budget_min = budget * 0.75
    budget_max = budget * 1.15

    filtered = build_df[
        (build_df['Total_Price'] >= budget_min) &
        (build_df['Total_Price'] <= budget_max)
    ].copy()

    # Loại bỏ các bộ PC đã gợi ý trước đó (nếu có)
    if exclude_builds and not filtered.empty:
        filtered = filtered[~filtered['BuildID'].isin(exclude_builds)]

    if filtered.empty:
        return None

    user_msg_lower = user_message.lower()

    # Tính điểm mục đích
    filtered['_purpose_score'] = filtered['Build_Notes'].fillna('').apply(
        lambda notes: _score_purpose(notes, user_msg_lower)
    )

    # Tính điểm gần budget (càng gần budget gốc càng tốt)
    filtered['_budget_score'] = 1.0 - (
        (filtered['Total_Price'] - budget).abs() / budget
    ).clip(upper=1.0)

    # Điểm tổng hợp: mục đích ưu tiên cao hơn, budget là tiebreaker
    filtered['_combined_score'] = (
        filtered['_purpose_score'] * 2.0 +
        filtered['_budget_score'] * 1.0
    )

    best_row = filtered.sort_values('_combined_score', ascending=False).iloc[0]

    # Dọn dẹp cột tạm trước khi trả về
    result = best_row.to_dict()
    for col in ['_purpose_score', '_budget_score', '_combined_score']:
        result.pop(col, None)

    return result


# ──────────────────────────────────────────────
# Format giá dạng “kẻ xấp xỉ X triệu” thay vì số chính xác
# ──────────────────────────────────────────────
def _format_approx_million(vnd: float) -> str:
    """
    Chuyển giá VNĐ sang dạng xấp xỉ triệu đồng.
    Ví dụ: 25_250_500 → “kẻ xấp xỉ 25.3 triệu”
             300_000  → “kẻ xấp xỉ 0.3 triệu”
    """
    try:
        millions = round(float(vnd) / 1_000_000, 1)
        # Trường hợp số nguyên → bỏ phần thập phân .0
        if millions == int(millions):
            return f"~{int(millions)} triệu"
        return f"~{millions} triệu"
    except (TypeError, ValueError):
        return "N/A"


# ──────────────────────────────────────────────
# Format context đưa vào LLM
# ──────────────────────────────────────────────
def format_build_context(build: dict) -> str:
    """
    Chuyển dict bộ PC thành chuỗi context để inject vào prompt.
    Giá được hiển thị dạng xấp xỉ triệu (“~X.X triệu”) thay vì số chính xác.
    """
    if not build:
        return ""

    total_price  = _format_approx_million(build.get('Total_Price', 0))
    cpu_price    = _format_approx_million(build.get('Component_Price_CPU', 0))
    gpu_price    = _format_approx_million(build.get('Component_Price_GPU', 0))
    main_price   = _format_approx_million(build.get('Component_Price_Motherboard', 0))
    assembly_fee = _format_approx_million(build.get('Assembly_Fee', 0))
    print(f"DEBUG: Build context - Build: {build.get('BuildID', 'N/A')}")

    return (
        f"[GỢI Ý BỘ PC TỐI ƯU]\n"
        f"- Mã bộ     : {build.get('BuildID', 'N/A')}\n"
        f"- CPU       : {build.get('CPU_Model', 'N/A')} | Giá: {cpu_price}\n"
        f"- GPU       : {build.get('GPU_Model', 'N/A')} | Giá: {gpu_price}\n"
        f"- Mainboard : {build.get('Motherboard_Model', 'N/A')} | Giá: {main_price}\n"
        f"- Phí lắp ráp: {assembly_fee}\n"
        f"- Tổng cộng : {total_price}\n"
        f"- Phù hợp cho: {build.get('Build_Notes', '')}\n"
    )
