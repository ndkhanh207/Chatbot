import re
from .constants import (
    BUILD_PC_TRIGGERS, BUILD_PC_REGEX_PATTERNS, PURPOSE_KEYWORD_MAP, PERIPHERAL_BRAND_MAP,
    ADJUSTMENT_LOCK_KEYWORDS, ADJUSTMENT_SWAP_KEYWORDS, ADJUSTMENT_BUDGET_KEYWORDS, BRAND_SWITCH_KEYWORDS
)
from app.core.intent.history_context import CPU_RE, GPU_RE, MAIN_RE, CAT_RE
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
    'không cần', 'bỏ qua', 'bộ mới hoàn toàn', 'quên hết đi',
    'làm lại từ đầu', 'quên hết', 'bỏ qua hết', 'reset', 'forgot all'
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

    gpu_m = GPU_RE.search(msg_lower)
    if gpu_m:
        gpu_model = gpu_m.group(0).strip()

    cpu_m = CPU_RE.search(msg_lower)
    if cpu_m:
        cpu_model = cpu_m.group(0).strip()
        
    mainboard = None
    main_m = MAIN_RE.search(msg_lower)
    if main_m:
        mainboard = main_m.group(1).strip()
        
    category = None
    cat_m = CAT_RE.search(msg_lower)
    if cat_m:
        category = cat_m.group(1).lower().strip()

    return {'gpu_model': gpu_model, 'cpu_model': cpu_model, 'mainboard': mainboard, 'category': category}

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

def extract_build_adjustment(msg: str, last_build: dict) -> dict | None:
    """
    Phát hiện user muốn điều chỉnh cấu hình đang tư vấn.
    """
    msg_lower = msg.lower()
    adjustment = {
        'type': None,
        'new_budget': None,
        'lock': {'cpu': False, 'gpu': False, 'mainboard': False},
        'swap': {'cpu_model': None, 'gpu_model': None, 'mainboard_model': None},
        'brand': None
    }
    
    # 1. Brand switch
    if any(kw in msg_lower for kw in BRAND_SWITCH_KEYWORDS):
        adjustment['type'] = 'brand_switch'
        if 'amd' in msg_lower:
            adjustment['brand'] = 'AMD'
        elif 'intel' in msg_lower:
            adjustment['brand'] = 'Intel'
        elif 'nvidia' in msg_lower:
            adjustment['brand'] = 'NVIDIA'
        return adjustment
    comp = extract_component_filter(msg)
    from app.core.intent.history_context import MAIN_RE
    m_main = MAIN_RE.search(msg_lower)
    main_model = m_main.group(1) if m_main else None

    # Phân tích xem linh kiện nào đi với lệnh nào (lock hay swap) bằng khoảng cách
    cpu_idx = min([msg_lower.find(w) for w in ['cpu', 'chip', 'vi xử lý'] if msg_lower.find(w) != -1], default=-1)
    if cpu_idx == -1 and comp.get('cpu_model'):
        cpu_idx = msg_lower.find(comp['cpu_model'].lower())

    gpu_idx = min([msg_lower.find(w) for w in ['gpu', 'vga', 'card'] if msg_lower.find(w) != -1], default=-1)
    if gpu_idx == -1 and comp.get('gpu_model'):
        gpu_idx = msg_lower.find(comp['gpu_model'].lower())

    main_idx = min([msg_lower.find(w) for w in ['main', 'mainboard', 'bo mạch chủ'] if msg_lower.find(w) != -1], default=-1)
    if main_idx == -1 and main_model:
        main_idx = msg_lower.find(main_model.lower())

    lock_idx = -1
    lock_kw_len = 0
    msg_for_swap = msg_lower
    for w in ADJUSTMENT_LOCK_KEYWORDS:
        idx = msg_lower.find(w)
        if idx != -1:
            if lock_idx == -1 or idx < lock_idx:
                lock_idx = idx
                lock_kw_len = len(w)
            # Xoá từ khoá lock khỏi chuỗi để tránh bị dính từ khoá swap (vd: "không đổi" chứa chữ "đổi")
            msg_for_swap = msg_for_swap.replace(w, ' ' * len(w))

    swap_idx = -1
    swap_kw_len = 0
    for w in ADJUSTMENT_SWAP_KEYWORDS:
        idx = msg_for_swap.find(w)
        if idx != -1:
            if swap_idx == -1 or idx < swap_idx:
                swap_idx = idx
                swap_kw_len = len(w)

    is_swap = swap_idx != -1
    is_lock = lock_idx != -1

    def get_intent(comp_idx):
        if comp_idx == -1: return None
        if not is_swap and is_lock: return 'lock'
        if is_swap and not is_lock: return 'swap'
        if is_swap and is_lock:
            # Chọn cái gần hơn dựa trên khoảng cách thực tế (bỏ qua độ dài từ khoá)
            def dist(idx, kw_len):
                if comp_idx >= idx + kw_len:
                    return comp_idx - (idx + kw_len)
                elif comp_idx < idx:
                    return idx - comp_idx
                return 0

            dist_to_lock = dist(lock_idx, lock_kw_len)
            dist_to_swap = dist(swap_idx, swap_kw_len)
            print(f"DEBUG get_intent comp_idx={comp_idx} lock=({lock_idx},{lock_kw_len})->{dist_to_lock} swap=({swap_idx},{swap_kw_len})->{dist_to_swap}")
            return 'lock' if dist_to_lock < dist_to_swap else 'swap'
        return None

    if is_swap or is_lock:
        adjustment['type'] = 'swap_component' if is_swap else 'lock_component'
        
        comp = extract_component_filter(msg)
        adjustment['swap']['cpu_model'] = comp.get('cpu_model')
        adjustment['swap']['gpu_model'] = comp.get('gpu_model')
        from app.core.intent.history_context import MAIN_RE
        m_main = MAIN_RE.search(msg_lower)
        if m_main:
            adjustment['swap']['mainboard_model'] = m_main.group(1)

        adjustment['swap']['target_cpu'] = get_intent(cpu_idx) == 'swap'
        adjustment['swap']['target_gpu'] = get_intent(gpu_idx) == 'swap'
        adjustment['swap']['target_main'] = get_intent(main_idx) == 'swap'
        
        adjustment['lock']['cpu'] = get_intent(cpu_idx) == 'lock'
        adjustment['lock']['gpu'] = get_intent(gpu_idx) == 'lock'
        adjustment['lock']['mainboard'] = get_intent(main_idx) == 'lock'

    # 4. Budget change
    is_budget = any(kw in msg_lower for kw in ADJUSTMENT_BUDGET_KEYWORDS)
    if is_budget and not is_swap and not is_lock:
        new_budget = extract_budget(msg, context_aware=True)
        if new_budget:
            adjustment['type'] = 'budget_change'
            adjustment['new_budget'] = new_budget
            return adjustment
            
        # Xử lý +/- budget
        m_delta = re.search(r'\b(rẻ hơn|đắt hơn|giảm|tăng thêm)\s*(\d+)\s*(triệu|tr|m)\b', msg_lower)
        if m_delta:
            delta_val = int(m_delta.group(2)) * 1_000_000
            adjustment['type'] = 'budget_change'
            adjustment['new_budget'] = delta_val # Sẽ cộng/trừ trong flow
            if 'rẻ hơn' in msg_lower or 'giảm' in msg_lower:
                adjustment['new_budget'] = -delta_val
            return adjustment

    # 5. Priority change
    from .constants import ADJUSTMENT_PRIORITY_KEYWORDS
    is_priority = any(kw in msg_lower for kw in ADJUSTMENT_PRIORITY_KEYWORDS)
    if is_priority and not is_swap and not is_lock and not is_budget:
        adjustment['type'] = 'priority_change'
        return adjustment

    if adjustment['type']:
        return adjustment
    return None

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

def extract_priority_bias(msg: str) -> dict | None:
    """
    Phát hiện user muốn ưu tiên component nào (dành cho PC Builder).
    Trả về: {'gpu_heavy': bool, 'cpu_heavy': bool, 'purpose_bias': str | None}
    """
    msg_lower = msg.lower()
    from .constants import ADJUSTMENT_PRIORITY_KEYWORDS
    
    if not any(kw in msg_lower for kw in ADJUSTMENT_PRIORITY_KEYWORDS):
        return None

    # Phân tích component bias
    gpu_idx = min([msg_lower.find(w) for w in ['gpu', 'card', 'vga'] if msg_lower.find(w) != -1], default=-1)
    cpu_idx = min([msg_lower.find(w) for w in ['cpu', 'chip'] if msg_lower.find(w) != -1], default=-1)
    
    gpu_heavy = False
    cpu_heavy = False
    
    # Nếu nhắc đến cả 2, so khoảng cách hoặc xem cái nào đứng trước
    # Nhưng nếu chỉ nhắc GPU (VD: "ưu tiên GPU"), thì gpu_heavy = True
    if gpu_idx != -1 and (cpu_idx == -1 or gpu_idx < cpu_idx):
        gpu_heavy = True
    elif cpu_idx != -1 and (gpu_idx == -1 or cpu_idx < gpu_idx):
        cpu_heavy = True

    # Phân tích purpose bias
    purpose_bias = None
    if any(kw in msg_lower for kw in ['esport', 'esports', 'moba', 'fps nhẹ']):
        purpose_bias = 'esport'
    elif any(kw in msg_lower for kw in ['workstation', 'render', 'máy trạm']):
        purpose_bias = 'workstation'
    elif any(kw in msg_lower for kw in ['game aaa', '4k', 'nặng']):
        purpose_bias = 'game_aaa'

    return {'gpu_heavy': gpu_heavy, 'cpu_heavy': cpu_heavy, 'purpose_bias': purpose_bias}

