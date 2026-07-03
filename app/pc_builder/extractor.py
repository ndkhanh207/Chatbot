# app/pc_builder/extractor.py
import re
from .constants import BUILD_PC_TRIGGERS, BUILD_PC_REGEX_PATTERNS, PURPOSE_KEYWORD_MAP

# ──────────────────────────────────────────────
# Intent detection
# ──────────────────────────────────────────────
def detect_build_pc_intent(msg: str) -> bool:
    """
    Trả về True nếu user đang hỏi về gợi ý bộ PC trọn bộ.
    Dùng kết hợp: literal triggers (nhanh) + regex patterns (linh hoạt).
    Đây là safety-net — chỉ dùng khi LLM trả intent = 'none'.
    """
    msg_lower = msg.lower()

    # Kiểm tra literal triggers trước (O(n) nhanh)
    if any(trigger in msg_lower for trigger in BUILD_PC_TRIGGERS):
        return True

    # Kiểm tra regex patterns (linh hoạt hơn, bắt biến thể tự nhiên)
    for pattern in BUILD_PC_REGEX_PATTERNS:
        if re.search(pattern, msg_lower):
            return True

    return False


RESET_INTENT_KEYWORDS = [
    'bộ khác', 'cái khác', 'hoàn toàn khác', 'thay đổi hết',
    'không cần', 'bỏ qua', 'bộ mới hoàn toàn'
]

def is_reset_intent(msg: str) -> bool:
    """Kiểm tra xem user có muốn build bộ mới hoàn toàn (không kế thừa) không."""
    msg_lower = msg.lower()
    return any(kw in msg_lower for kw in RESET_INTENT_KEYWORDS)

# ──────────────────────────────────────────────
# Trích xuất thông tin
# ──────────────────────────────────────────────
def extract_budget(msg: str, context_aware: bool = False) -> int | None:
    """
    Trích xuất ngân sách (VNĐ) từ câu hỏi của user.
    Ví dụ: '30 triệu' → 30_000_000, '15tr' → 15_000_000, '100k' → 100_000

    Tham số:
        context_aware: Nếu True (AI vừa hỏi ngân sách), nhận dạng thêm:
                       - Số nguyên thuần: '20' → 20 triệu
                       - Số thập phân: '1.5' → 1.5 triệu = 1_500_000
                       - VNĐ thô: '20000000' → 20 triệu
    """
    msg_lower = msg.lower().replace(',', '.')
    # Xử lý chữ "âm" đứng trước số (ví dụ: "âm 30 triệu" -> "-30 triệu")
    msg_lower = re.sub(r'\bâm\s+(\d)', r'-\1', msg_lower)

    # Rule 1: "20 triệu", "20tr", "20m"
    m1 = re.search(r'(-?\d+(?:\.\d+)?)\s*(triệu|tr\b|m\b)', msg_lower)
    if m1:
        return int(float(m1.group(1)) * 1_000_000)

    msg_no_space = msg_lower.replace(' ', '')

    # Rule 2: "20000000" (VNĐ thô, không dấu cách)
    m2 = re.search(r'(-?\d+)000000\b', msg_no_space)
    if m2:
        return int(float(m2.group(1)) * 1_000_000)

    # Rule 3: "20k000" (ít dùng, phòng thủ)
    m3 = re.search(r'(-?\d+(?:\.\d+)?)k000\b', msg_no_space)
    if m3:
        return int(float(m3.group(1)) * 1_000_000)

    # Rule 4: "100k" (trăm nghìn)
    m4 = re.search(r'(-?\d+(?:\.\d+)?)\s*k\b', msg_lower)
    if m4:
        return int(float(m4.group(1)) * 1_000)

    # Rule 5 (context_aware): Nhận số thuần khi AI đang hỏi ngân sách
    # VD: "20", "1.5", "20000000" → suy ra đơn vị
    if context_aware:
        m5 = re.search(r'^\s*(-?\d+(?:[.,]\d+)?)\s*$', msg.strip())
        if m5:
            val = float(m5.group(1).replace(',', '.'))
            if val > 1_000_000:
                # VNĐ thô (VD: "20000000") → trả nguyên
                return int(val)
            if 1 <= val <= 999:
                # Hiểu là triệu (VD: "20" → 20 triệu)
                return int(val * 1_000_000)

    return None


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


def extract_brand_filter(msg: str) -> dict:
    """
    Trả về dict {'cpu_brand': str|None, 'gpu_brand': str|None, 'any_brand': str|None}.
    """
    msg_lower = msg.lower()
    cpu_brand = None
    gpu_brand = None
    any_brand = None

    m_cpu = re.search(r'\b(cpu|chip|vi xử lý)\s+(intel|amd)\b', msg_lower)
    if m_cpu:
        cpu_brand = 'Intel' if m_cpu.group(2) == 'intel' else 'AMD'

    m_gpu = re.search(r'\b(gpu|vga|card)\s+(nvidia|amd)\b', msg_lower)
    if m_gpu:
        gpu_brand = 'NVIDIA' if m_gpu.group(2) == 'nvidia' else 'AMD'

    if not cpu_brand and not gpu_brand:
        if re.search(r'\bintel\b', msg_lower):
            cpu_brand = 'Intel'
        elif re.search(r'\bnvidia\b', msg_lower):
            gpu_brand = 'NVIDIA'
        elif re.search(r'\bamd\b', msg_lower):
            any_brand = 'AMD'

    return {'cpu_brand': cpu_brand, 'gpu_brand': gpu_brand, 'any_brand': any_brand}


def extract_component_filter(msg: str) -> dict:
    """
    Phát hiện nếu user yêu cầu một CPU/GPU model cụ thể.
    """
    msg_lower = msg.lower()
    gpu_model = None
    cpu_model = None

    gpu_m = re.search(r'\b(rtx|gtx|rx|arc)\s*(\d{3,5}(?:\s*ti|\s*xt|\s*xtx|)?)\b', msg_lower)
    if gpu_m:
        gpu_model = gpu_m.group(0).strip()

    cpu_m = re.search(
        r'\b(i[3579](?:-?\d{4,5}[a-z]*)?|ryzen\s*[3579](?:\s*\d{3,5}[a-z]*)?|core\s*ultra\s*\d+|x3d)\b',
        msg_lower
    )
    if cpu_m:
        cpu_model = cpu_m.group(0).strip()

    return {'gpu_model': gpu_model, 'cpu_model': cpu_model}


def extract_explicit_build_id(msg: str) -> str | None:
    """
    Phát hiện nếu user nhắc thẳng một mã BuildID cụ thể trong câu hỏi.
    Sử dụng negative lookahead để tránh bắt nhầm 'build 1 bộ', 'build 2 máy'.
    """
    # Bắt 'build-1', 'build_1' HOẶC 'build 1' (nhưng không đi kèm bộ/máy/pc...)
    m = re.search(r'\bbuild[-_](\d+)\b|\bbuild\s+(\d+)\b(?!\s*(?:bộ|máy|pc|cái|chiếc))', msg, re.IGNORECASE)
    if m:
        num = m.group(1) or m.group(2)
        return f"BUILD-{num}"
    return None


def infer_purpose(combined_msg: str) -> str:
    """
    Nội suy mục đích sử dụng từ câu hỏi dựa trên PURPOSE_KEYWORD_MAP.
    Ưu tiên theo thứ tự: game aaa > render > đồ họa > ai > stream > lập trình > game > văn phòng.
    """
    msg_lower = combined_msg.lower()

    # Thứ tự ưu tiên (đặc biệt trước, chung chung sau)
    priority_order = ['game aaa', 'render', 'đồ họa', 'ai', 'stream', 'lập trình', 'game', 'văn phòng']

    for purpose in priority_order:
        keywords = PURPOSE_KEYWORD_MAP.get(purpose, [])
        if any(kw in msg_lower for kw in keywords):
            return purpose

    return 'sử dụng'
