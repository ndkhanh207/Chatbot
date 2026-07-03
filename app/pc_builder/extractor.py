import re
from .constants import BUILD_PC_TRIGGERS, PURPOSE_KEYWORD_MAP, PERIPHERAL_BRAND_MAP

# ──────────────────────────────────────────────
# Intent detection
# ──────────────────────────────────────────────
def detect_build_pc_intent(msg: str) -> bool:
    """Trả về True nếu user đang hỏi về gợi ý bộ PC trọn bộ."""
    msg_lower = msg.lower()
    return any(trigger in msg_lower for trigger in BUILD_PC_TRIGGERS)

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
def extract_budget(msg: str) -> int | None:
    """
    Trích xuất ngân sách (VNĐ) từ câu hỏi của user.
    Ví dụ: '30 triệu' → 30_000_000, '15tr' → 15_000_000, '100k' → 100_000
    Trả về None nếu không tìm thấy, hoặc số âm nếu phát hiện số âm.
    """
    msg_lower = msg.lower().replace(',', '.')

    m1 = re.search(r'(-?\d+(?:\.\d+)?)\s*(triệu|tr\b|m\b)', msg_lower)
    if m1: return int(float(m1.group(1)) * 1_000_000)

    msg_no_space = msg_lower.replace(' ', '')
    
    m2 = re.search(r'(-?\d+)000000\b', msg_no_space)
    if m2: return int(float(m2.group(1)) * 1_000_000)

    m3 = re.search(r'(-?\d+(?:\.\d+)?)k000\b', msg_no_space)
    if m3: return int(float(m3.group(1)) * 1_000_000)

    m4 = re.search(r'(-?\d+(?:\.\d+)?)\s*k\b', msg_lower)
    if m4: return int(float(m4.group(1)) * 1_000)

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
        else:
            for kw, brand in PERIPHERAL_BRAND_MAP.items():
                if kw in msg_lower:
                    any_brand = brand
                    break

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

def extract_upgrade_component(msg: str) -> dict:
    """
    Phát hiện kịch bản nâng cấp: user đã có sẵn CPU/GPU và muốn build phần còn lại.
    Trả về: {'cpu_model': str, 'gpu_model': str, 'is_upgrade': bool}
    """
    msg_lower = msg.lower()
    is_upgrade = bool(re.search(r'\b(đã có|đang có|có sẵn|tôi có|giữ lại|tận dụng)\b', msg_lower))
    
    if not is_upgrade:
        return {'cpu_model': None, 'gpu_model': None, 'is_upgrade': False}
        
    comp = extract_component_filter(msg)
    return {
        'cpu_model': comp.get('cpu_model'),
        'gpu_model': comp.get('gpu_model'),
        'is_upgrade': True
    }


def extract_explicit_build_id(msg: str) -> str | None:
    """
    Phát hiện nếu user nhắc thẳng một mã BuildID cụ thể trong câu hỏi.
    """
    m = re.search(r'\bbuild[-_\s]?(\d+)\b', msg, re.IGNORECASE)
    if m:
        return f"BUILD-{m.group(1)}"
    return None

def infer_purpose(combined_msg: str) -> str:
    """Nội suy mục đích từ câu hỏi."""
    msg_lower = combined_msg.lower()
    for kw in ['văn phòng', 'tiệm net', 'chơi game aaa', 'chơi game', 'render',
               'đồ họa', 'lập trình', 'deep learning', 'ai', 'stream']:
        if kw in msg_lower:
            return kw
    return 'sử dụng'
