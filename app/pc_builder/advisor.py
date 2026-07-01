# pc_build_advisor.py
"""
Module tư vấn bộ PC trọn gói (CPU + GPU + Mainboard).
Tìm kiếm bộ PC phù hợp nhất dựa trên ngân sách và mục đích sử dụng
từ file data/Pc_build_data.csv.
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
    'pc gaming', 'máy gaming', 'bộ khác', 'cấu hình khác',
    # Thêm các trường hợp máy đặc thù
    'tiệm net', 'phòng máy', 'quán net', 'máy trạm',
    'workstation', 'bộ máy', 'máy chơi game',
    'bộ pc intel', 'bộ pc amd', 'pc intel', 'pc amd',
    'bộ pc nvidia', 'pc nvidia', 'pc render', 'pc đồ họa', 'pc ai',
    'build 1 máy', 'build một máy', 'build máy', 'máy văn phòng',
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
    'lập trình': ['lập trình', 'máy ảo', 'data science', 'xử lý dữ liệu', 'code', 'dev'],
    'văn phòng': [
        'văn phòng', 'word', 'excel', 'học tập', 'lướt web', 'cơ bản', 'tiệm net', 'quán net',
        'chung chung', 'bình thường', 'giải trí nhẹ', 'không có nhu cầu đặc biệt', 'đa dụng'
    ],
    # FEATURE: Bổ sung từ khóa AI/Deep Learning
    'ai': [
        'deep learning', 'huấn luyện ai', 'ai', 'machine learning',
        'ml', 'dl', 'train model', 'training model',
        'data science', 'xử lý dữ liệu nặng', 'workstation ai',
        'neural network', 'pytorch', 'tensorflow',
    ],
    'stream':  ['stream game', 'stream đa nền tảng', 'stream'],
}

# ──────────────────────────────────────────────
# Brand filter mapping
# ──────────────────────────────────────────────
CPU_BRAND_MAP = {
    'intel': 'Intel',
    'amd':   'AMD',
}
GPU_BRAND_MAP = {
    'nvidia': 'Nvidia',
    'amd':    'AMD',
    'intel':  'Intel',  # Intel Arc
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
    Ví dụ: '30 triệu' → 30_000_000, '15tr' → 15_000_000, '100k' → 100_000
    Trả về None nếu không tìm thấy, hoặc số âm nếu phát hiện số âm.
    """
    msg_lower = msg.lower().replace(',', '.')

    # 1. Pattern triệu/tr/m (ví dụ: 30tr, -30 triệu, 30.5m)
    m1 = re.search(r'(-?\d+(?:\.\d+)?)\s*(triệu|tr\b|m\b)', msg_lower)
    if m1: return int(float(m1.group(1)) * 1_000_000)

    # Các pattern với số 0 liền kề thì xóa khoảng trắng để dễ bắt (vd: 30 000 000)
    msg_no_space = msg_lower.replace(' ', '')
    
    # 2. Pattern 30000000
    m2 = re.search(r'(-?\d+)000000\b', msg_no_space)
    if m2: return int(float(m2.group(1)) * 1_000_000)

    # 3. Pattern k000 (30k000)
    m3 = re.search(r'(-?\d+(?:\.\d+)?)k000\b', msg_no_space)
    if m3: return int(float(m3.group(1)) * 1_000_000)

    # 4. Pattern k (ví dụ: -100k, 100k)
    m4 = re.search(r'(-?\d+(?:\.\d+)?)\s*k\b', msg_lower)
    if m4: return int(float(m4.group(1)) * 1_000)

    return None


# ──────────────────────────────────────────────
# Trích xuất số lượng bộ PC (BUG 2)
# ──────────────────────────────────────────────
def extract_quantity(msg: str) -> int:
    """
    Phát hiện số lượng bộ PC user muốn mua.
    Ví dụ: "10 bộ", "5 máy", "3 cái" → trả về số đó.
    Mặc định là 1.
    """
    msg_lower = msg.lower()
    patterns = [
        r'(\d+)\s*(?:bộ|máy|cái|chiếc|pc)\b',
        r'mua\s*(\d+)',
        r'(\d+)\s*bộ\s*pc',
    ]
    for pattern in patterns:
        m = re.search(pattern, msg_lower)
        if m:
            qty = int(m.group(1))
            if qty > 1:
                return qty
    return 1


# ──────────────────────────────────────────────
# Trích xuất brand filter từ câu hỏi (BUG 5)
# ──────────────────────────────────────────────
def extract_brand_filter(msg: str) -> dict:
    """
    Trả về dict {'cpu_brand': str|None, 'gpu_brand': str|None, 'any_brand': str|None}.
    - Nếu ghi rõ "cpu intel", "vga nvidia" -> gán đúng cpu_brand/gpu_brand
    - Nếu chỉ ghi "intel", gán cpu_brand="Intel"
    - Nếu chỉ ghi "nvidia", gán gpu_brand="NVIDIA"
    - Nếu chỉ ghi "amd", gán any_brand="AMD"
    """
    msg_lower = msg.lower()
    cpu_brand = None
    gpu_brand = None
    any_brand = None

    # Tìm cụm từ rõ ràng (VD: cpu intel, vga nvidia)
    m_cpu = re.search(r'\b(cpu|chip|vi xử lý)\s+(intel|amd)\b', msg_lower)
    if m_cpu:
        cpu_brand = 'Intel' if m_cpu.group(2) == 'intel' else 'AMD'

    m_gpu = re.search(r'\b(gpu|vga|card)\s+(nvidia|amd)\b', msg_lower)
    if m_gpu:
        gpu_brand = 'NVIDIA' if m_gpu.group(2) == 'nvidia' else 'AMD'

    # Nếu không ghi rõ cpu/gpu mà chỉ gọi tên hãng
    if not cpu_brand and not gpu_brand:
        if re.search(r'\bintel\b', msg_lower):
            cpu_brand = 'Intel'
        elif re.search(r'\bnvidia\b', msg_lower):
            gpu_brand = 'NVIDIA'
        elif re.search(r'\bamd\b', msg_lower):
            any_brand = 'AMD'

    return {'cpu_brand': cpu_brand, 'gpu_brand': gpu_brand, 'any_brand': any_brand}


# ──────────────────────────────────────────────
# Trích xuất tên model linh kiện cụ thể (BUG 6)
# ──────────────────────────────────────────────
def extract_component_filter(msg: str) -> dict:
    """
    Phát hiện nếu user yêu cầu một CPU/GPU model cụ thể.
    Ví dụ: "build pc có rtx 5090" → {'gpu_model': 'rtx 5090', 'cpu_model': None}
    """
    msg_lower = msg.lower()

    gpu_model = None
    cpu_model = None

    # GPU patterns: rtx/gtx/rx + số
    gpu_m = re.search(r'\b(rtx|gtx|rx|arc)\s*(\d{3,5}(?:\s*ti|\s*xt|\s*xtx|)?)\b', msg_lower)
    if gpu_m:
        gpu_model = gpu_m.group(0).strip()

    # CPU patterns: i3/i5/i7/i9-XXXXX hoặc ryzen X XXXX hoặc x3d
    cpu_m = re.search(
        r'\b(i[3579](?:-?\d{4,5}[a-z]*)?|ryzen\s*[3579](?:\s*\d{3,5}[a-z]*)?|core\s*ultra\s*\d+|x3d)\b',
        msg_lower
    )
    if cpu_m:
        cpu_model = cpu_m.group(0).strip()

    return {'gpu_model': gpu_model, 'cpu_model': cpu_model}


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

    Args:
        budget:           Ngân sách của user (VNĐ).
        user_message:     Câu hỏi gốc của user (dùng để score mục đích).
        build_df:         DataFrame từ Pc_build_data.csv.
        exclude_builds:   List các BuildID cần loại trừ.
        brand_filter:     {'cpu_brand': str|None, 'gpu_brand': str|None}
        component_filter: {'gpu_model': str|None, 'cpu_model': str|None}
        find_cheapest:    Nếu True → tìm bộ rẻ nhất, bỏ qua budget filter.

    Returns:
        dict chứa thông tin bộ PC, hoặc None nếu không tìm được.
    """
    if build_df is None or build_df.empty:
        return None

    filtered = build_df.copy()

    # BUG 6: Filter theo component model cụ thể trước
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

    # BUG 5: Filter theo brand CPU/GPU
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
                (filtered['GPU_Brand'].str.lower() == any_brand.lower())
            ]
        
        if filtered.empty:
            return None

    # BUG 4: Nếu tìm rẻ nhất → không filter theo budget
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
    filtered = filtered.copy()
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
# Format giá dạng "~X triệu" thay vì số chính xác
# ──────────────────────────────────────────────
def _format_approx_million(vnd: float) -> str:
    """
    Chuyển giá VNĐ sang dạng xấp xỉ triệu đồng.
    Ví dụ: 25_250_500 → "~25.3 triệu"
    """
    try:
        millions = round(float(vnd) / 1_000_000, 1)
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
def extract_explicit_build_id(msg: str) -> str | None:
    """
    Phát hiện nếu user nhắc thẳng một mã BuildID cụ thể trong câu hỏi.
    Ví dụ: "bộ pc BUILD-12345 có chơi được aaa không" -> "BUILD-12345"
            "build-03909 chơi game được không"        -> "BUILD-03909"
    """
    m = re.search(r'\bbuild[-_\s]?(\d+)\b', msg, re.IGNORECASE)
    if m:
        return f"BUILD-{m.group(1)}"
    return None