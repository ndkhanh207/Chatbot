import re
from typing import Optional, Tuple, List, Dict, Any, Callable
from app.constants import *
import pandas as pd
import functools

# ──────────────────────────────────────────────
# 1. TIER MAINBOARD (Đánh giá theo chất lượng dàn điện VRM)
# ──────────────────────────────────────────────
CHIPSET_PREFIX_TIER: Dict[str, int] = {
    "H": 1, "A": 1,        # Tier 1 (Entry): H410/H610, A520/A620 -> Dàn điện yếu, chỉ nên gánh i3/R3.
    "B": 2,                # Tier 2 (Mid): B660/B760, B550/B650 -> Dàn điện tốt, gánh mượt i5/R5, cố được i7 non-K.
    "Z": 3, "X": 3,        # Tier 3 (High): Z690/Z790, X670/X870 -> Dàn điện khủng, gánh i7/i9, R7/R9, tối ưu ép xung.
    "W": 4, "TRX": 4       # Tier 4 (HEDT): Dành riêng cho Xeon, Threadripper.
}
_CHIPSET_PATTERN = re.compile(r"\b([A-Z])(\d{3})([A-Z]{0,2})?\b", re.IGNORECASE)

# ──────────────────────────────────────────────
# 2. TIER CPU (Đánh giá theo hiệu năng và sức ăn điện thực tế - MTP/PL2)
# ──────────────────────────────────────────────
CPU_LINE_TIER: Dict[str, int] = {
    "3": 1,     # Core i3 / Ryzen 3
    "5": 2,     # Core i5 / Ryzen 5
    "7": 3,     # Core i7 / Ryzen 7
    "9": 4      # Core i9 / Ryzen 9
}

# [BƯỚC ĐỘT PHÁ] - Điểm cộng trừ dựa trên hậu tố CPU
# Hậu tố quyết định cực lớn đến lượng điện bú thêm khi Turbo.
# ⚠️ Key dài hơn PHẢI đặt TRƯỚC key ngắn (VD: "X3D" trước "X")
#    vì matching dùng longest-first để tránh "X" match nhầm "X3D".
CPU_SUFFIX_MODIFIER: Dict[str, int] = {
    "KS": 1, "KF": 1, "K": 1,            # Intel Unlocked: Ăn cực nhiều điện -> Ép lên 1 Tier Mainboard
    "X3D": 0,                             # AMD 3D V-Cache: Tiết kiệm điện (120W), main B tầm trung gánh tốt -> Giữ nguyên
    "XT": 0, "X": 0,                     # AMD Extreme: Ăn nhiều điện hơn non-X nhưng ko ép lên Tier, chỉ set has_k_modifier để tránh dùng main Tier thấp nhất
    "F": 0, "": 0,                       # Dòng tiêu chuẩn không iGPU hoặc bình thường -> Giữ nguyên Tier
    "GE": -1, "G": -1,                   # Dòng tiết kiệm điện (có iGPU) -> Hạ 1 Tier
    "T": -1, "U": -1,                    # Dòng tiết kiệm điện -> Hạ 1 Tier (Main rẻ hơn vẫn gánh tốt)
}

# TDP bây giờ chỉ dùng làm phương án dự phòng (Fallback) nếu Regex gãy, không ưu tiên!
TDP_TIER_THRESHOLDS: List[Tuple[float, int]] = [
    (70.0, 1),   
    (130.0, 2),  
    (200.0, 3),
    (float("inf"), 4),
]

# ──────────────────────────────────────────────
# 3. PATTERNS & TỪ KHÓA
# ──────────────────────────────────────────────

COMPATIBILITY_TRIGGERS = [
    'tương thích', 'lắp được', 'chạy được', 'hợp không',
    'đi cùng', 'đi với', 'vừa không', 'cắm được', 'gắn được', 'kết hợp'
]


# CPU/GPU performance tier (cho gợi ý hiệu năng, KHÔNG phải giới hạn vật lý)
GPU_TIER_RANK = {50: 1, 60: 2, 70: 3, 80: 4, 90: 5}


_GPU_NVIDIA_PATTERN = re.compile(r'(?:rtx|gtx)\s*(\d{3,4})', re.IGNORECASE)
_GPU_AMD_PATTERN = re.compile(r'\brx\s*(\d{3,4})\b', re.IGNORECASE)
_CPU_INTEL_PATTERN = re.compile(r'i([3579])-(\d{4,5})([a-z]*)', re.IGNORECASE)
_CPU_AMD_PATTERN = re.compile(r'ryzen\s*([3579])\s+(\d{4,5})([a-z0-9]*)', re.IGNORECASE)


# ──────────────────────────────────────────────
# Helpers — parsing & lookup
# ──────────────────────────────────────────────
@functools.lru_cache(maxsize=1024)
def extract_chipset_code(name: str) -> Optional[str]:
    if not name:
        return None
    m = _CHIPSET_PATTERN.search(name)
    return (m.group(1) + m.group(2) + (m.group(3) or "")).upper() if m else None


@functools.lru_cache(maxsize=128)
def chipset_tier(chipset_code: Optional[str]) -> Optional[int]:
    """Tier theo CHỮ CÁI ĐẦU mã chipset (quy ước Intel/AMD), None nếu
    không nhận diện được — không đoán bừa."""
    return CHIPSET_PREFIX_TIER.get(chipset_code.strip()[0].upper()) if chipset_code and chipset_code.strip() else None


def required_tier_for_tdp(tdp: float) -> int:
    return next(tier for threshold, tier in TDP_TIER_THRESHOLDS if tdp <= threshold)


def max_tdp_for_tier(tier: int) -> float:
    return next((t for t, tr in TDP_TIER_THRESHOLDS if tr == tier), float("inf"))


@functools.lru_cache(maxsize=1024)
def normalize_socket(s: str) -> str:
    return re.sub(r"\s+", "", str(s)).upper() if s else ""


@functools.lru_cache(maxsize=1024)
def parse_pcie_gen(text: str) -> Optional[float]:
    m = re.search(r"pcie\s*(\d+(?:\.\d+)?)", str(text), re.IGNORECASE) if text else None
    return float(m.group(1)) if m else None


@functools.lru_cache(maxsize=1024)
def parse_gpu_profile(text: str) -> Optional[Dict[str, Any]]:
    """
    NVIDIA: 2 số cuối = tier band ('RTX 4080' → tier=80).
    AMD: chữ số hàng trăm × 10 = tier band ('RX 7900' → tier=90) —
    không dùng 2 số cuối vì AMD luôn kết thúc '00'.
    """
    if not text:
        return None
    m = _GPU_NVIDIA_PATTERN.search(text)
    if m:
        num = m.group(1)
        tier_band = int(num[-2:])
        generation_rank = int(num[:2]) // 10 if len(num) == 4 else None
        return {
            "brand": "nvidia", "tier_band": tier_band,
            "tier_rank": GPU_TIER_RANK.get(tier_band),
            "generation_rank": generation_rank,
        }
    m = _GPU_AMD_PATTERN.search(text)
    if m and len(m.group(1)) >= 2:
        num = m.group(1)
        tier_band = int(num[1]) * 10
        generation = int(num[0])
        generation_rank = min(5, (generation + 1) // 2)
        return {
            "brand": "amd", "tier_band": tier_band,
            "tier_rank": GPU_TIER_RANK.get(tier_band),
            "generation_rank": generation_rank,
        }
    return None


def _match_cpu_suffix(suffix: str) -> int:
    """Match hậu tố CPU theo longest-key-first để tránh 'X' match nhầm 'X3D'."""
    suffix = suffix.upper()
    # Sắp xếp key dài nhất trước → match chính xác nhất
    for key, mod in sorted(CPU_SUFFIX_MODIFIER.items(), key=lambda x: -len(x[0])):
        if key and key in suffix:
            return mod
    return CPU_SUFFIX_MODIFIER.get("", 0)


@functools.lru_cache(maxsize=1024)
def parse_cpu_profile(name: str) -> Optional[Dict[str, Any]]:
    """Tier chính từ dòng (i3=1...i9=4). Hậu tố X3D/G/T giảm hoặc giữ tier; K/KF/X ép lên."""
    if not name:
        return None
    for pattern, brand in ((_CPU_INTEL_PATTERN, "intel"), (_CPU_AMD_PATTERN, "amd")):
        m = pattern.search(name)
        if m:
            line, model, suffix = m.group(1), m.group(2), m.group(3).upper()
            modifier = _match_cpu_suffix(suffix)
            has_k = modifier > 0 or suffix in ["X", "XT"]
            generation = int(model[:-3]) if brand == "intel" else int(model[0])
            generation_rank = max(1, generation - 10) if brand == "intel" else (generation + 1) // 2
            return {
                "brand": brand,
                "tier_rank": max(1, CPU_LINE_TIER[line] + modifier),
                "generation_rank": generation_rank,
                "has_k_modifier": has_k,
            }
    return None


def _get_field(item: dict, *keys, default=None):
    return next((item[k] for k in keys if item.get(k) not in (None, "")), default)


def _category_df(kb: pd.DataFrame, category: str) -> pd.DataFrame:
    return kb[kb["category"] == category] if "category" in kb.columns else kb


def is_compatibility_query(message: str) -> bool:
    """Gate rẻ trước khi gọi parse_compat_intent (tránh tốn 1 lượt LLM
    cho mọi câu hỏi không liên quan compat)."""
    return any(t in message for t in COMPATIBILITY_TRIGGERS)


def assess_cpu_mainboard_tier(cpu_name: str, mainboard_name: str) -> Dict[str, Any]:
    """Assess CPU/mainboard power-tier fit using names only.

    This is useful outside the full compatibility path where socket fields may
    not be available, such as prebuilt PC review rows.
    """
    cpu_profile = parse_cpu_profile(cpu_name) or {}
    cpu_tier = cpu_profile.get("tier_rank")
    chipset = extract_chipset_code(mainboard_name)
    main_tier = chipset_tier(chipset)

    if cpu_tier is not None:
        required_tier = max(1, min(3, cpu_tier) - 1)
        tier_source = f"CPU Tier {cpu_tier}"
    else:
        required_tier = 1
        tier_source = "CPU Tier không rõ"

    tier_ok = main_tier is not None and main_tier >= required_tier
    return {
        "chipset": chipset,
        "main_tier": main_tier,
        "cpu_tier": cpu_tier,
        "required_tier": required_tier,
        "tier_source": tier_source,
        "tier_ok": tier_ok,
    }


def assess_cpu_gpu_balance(cpu_name: str, gpu_name: str) -> Dict[str, Any]:
    """Assess CPU/GPU balance using the same tier logic as compatibility."""
    check = check_cpu_gpu_compat(
        {"name": cpu_name, "tên": cpu_name},
        {"name": gpu_name, "tên": gpu_name, "chipset": gpu_name},
    )
    return {
        "cpu_tier": check.get("cpu_tier"),
        "gpu_tier": check.get("gpu_tier"),
        "warning": check.get("warning"),
        "is_compatible": check.get("is_compatible", True),
    }


# ──────────────────────────────────────────────
# Check 2 linh kiện cụ thể
# ──────────────────────────────────────────────
def check_cpu_main_compat(cpu: dict, main: dict) -> Dict[str, Any]:
    cpu_socket = normalize_socket(_get_field(cpu, "socket", "socket_type", default=""))
    main_socket = normalize_socket(_get_field(main, "socket", "socket_type", default=""))
    socket_match = bool(cpu_socket) and cpu_socket == main_socket

    chip_code = extract_chipset_code(_get_field(main, "tên", "name", default=""))
    main_tier = chipset_tier(chip_code)
    
    cpu_p = parse_cpu_profile(_get_field(cpu, "tên", "name", default=""))
    if cpu_p and "tier_rank" in cpu_p:
        cpu_tier = cpu_p["tier_rank"]
        tier_source = f"CPU Tier {cpu_tier}"
        required_tier = max(1, min(3, cpu_tier) - 1)
    else:
        cpu_tdp = float(_get_field(cpu, "tdp", default=0) or 0)
        required_tier = min(3, required_tier_for_tdp(cpu_tdp))
        tier_source = f"TDP {cpu_tdp}W (Tier {required_tier})"

    tier_ok = main_tier is not None and main_tier >= required_tier
    is_compatible = socket_match and tier_ok

    reasons = []
    if not socket_match:
        reasons.append(f"KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP): Socket không khớp. CPU dùng {cpu_socket or '(?)'}, mainboard dùng {main_socket or '(?)'}.")
    elif not tier_ok:
        if cpu_p and cpu_p.get("has_k_modifier"): 
             # Nếu là bản K/X/3D (Tier bị cộng lên)
             reasons.append(
                 f"KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP): Main Tier ({main_tier}) quá yếu so với {tier_source}. Bản K/X ăn nhiều điện, cắm main Tier {main_tier} có rủi ro tụt xung, suy giảm hiệu năng. Gợi ý lên Main Tier {required_tier}."
             )
        else:
             reasons.append(
                 f"KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP): Main Tier ({main_tier}) quá yếu so với {tier_source}. Mainboard không đủ khả năng cấp điện cho CPU."
             )
    else:
        reasons.append(f"Hoàn toàn TƯƠNG THÍCH (PHÙ HỢP): Socket khớp ({cpu_socket}), mainboard chipset {chip_code} (Tier {main_tier}) đủ gánh CPU ({tier_source}).")

    return {
        "is_compatible": is_compatible, "socket_match": socket_match,
        "chipset": chip_code, "main_tier": main_tier,
        "required_tier": required_tier, "reasons": reasons,
    }


def check_gpu_main_compat(gpu: dict, main: dict) -> Dict[str, Any]:
    gpu_gen = parse_pcie_gen(_get_field(gpu, "interface", "pcie", default=""))
    main_gen = parse_pcie_gen(_get_field(main, "pcie", "interface", default=""))

    warning = None
    if gpu_gen is not None and main_gen is not None and gpu_gen > main_gen:
        warning = (
            f"Hai linh kiện TƯƠNG THÍCH với nhau. Tuy nhiên GPU dùng PCIe {gpu_gen} nhưng mainboard chỉ hỗ trợ PCIe {main_gen}, "
            f"do đó băng thông PCIe {main_gen} sẽ không phát huy hết 100% sức mạnh của GPU."
        )

    return {"is_compatible": True, "gpu_pcie_gen": gpu_gen, "main_pcie_gen": main_gen, "warning": warning}


def check_cpu_gpu_compat(cpu: dict, gpu: dict) -> Dict[str, Any]:
    """Không có giới hạn vật lý — chỉ khuyến nghị tránh bottleneck rõ rệt."""
    cpu_p = parse_cpu_profile(_get_field(cpu, "tên", "name", default=""))
    gpu_p = parse_gpu_profile(_get_field(gpu, "chipset", "tên", "name", default=""))
    cpu_tier = cpu_p["tier_rank"] if cpu_p else None
    gpu_tier = gpu_p["tier_rank"] if gpu_p else None
    cpu_generation = cpu_p.get("generation_rank") if cpu_p else None
    gpu_generation = gpu_p.get("generation_rank") if gpu_p else None

    warning = None
    if cpu_tier is not None and gpu_tier is not None:
        cpu_score = cpu_tier + (cpu_generation or 0)
        gpu_score = gpu_tier + (gpu_generation or 0)
        if gpu_score < cpu_score - 1:
            warning = "GPU thuộc thế hệ cũ hoặc yếu hơn đáng kể so với CPU — GPU có thể là điểm nghẽn hiệu năng."
        elif cpu_score < gpu_score - 1:
            warning = "CPU thuộc thế hệ cũ hoặc yếu hơn đáng kể so với GPU — CPU có thể là điểm nghẽn hiệu năng."

    return {
        "is_compatible": True,
        "cpu_tier": cpu_tier, "gpu_tier": gpu_tier,
        "cpu_generation": cpu_generation, "gpu_generation": gpu_generation,
        "warning": warning,
    }


# ──────────────────────────────────────────────
# Collector chung + các hàm tìm theo category
# ──────────────────────────────────────────────
def _collect(kb: pd.DataFrame, category: str, check_fn: Callable[[dict], dict],
             require_compatible: bool = False, sort_no_warning_first: bool = False,
             sort_key: Optional[Callable[[dict], Any]] = None, top_k: int = 10) -> List[Dict[str, Any]]:
    results = []
    category_items = _category_df(kb, category).to_dict('records')
    for item in category_items:
        check = check_fn(item)
        if require_compatible and not check["is_compatible"]:
            continue
        results.append({"item": item, "compat": check})

    if sort_key:
        results.sort(key=sort_key)
    elif sort_no_warning_first:
        results.sort(key=lambda r: 1 if r["compat"].get("warning") else 0)
    return results[:top_k]


def find_compatible_mainboards(cpu: dict, kb: pd.DataFrame, top_k: int = 10):
    return _collect(kb, "MAINBOARD", lambda m: check_cpu_main_compat(cpu, m),
                     require_compatible=True, top_k=top_k)


def find_compatible_gpus_for_main(main: dict, kb: pd.DataFrame, top_k: int = 10):
    return _collect(kb, "GPU", lambda g: check_gpu_main_compat(g, main),
                     sort_no_warning_first=True, top_k=top_k)


def find_compatible_mains_for_gpu(gpu: dict, kb: pd.DataFrame, top_k: int = 10):
    return _collect(kb, "MAINBOARD", lambda m: check_gpu_main_compat(gpu, m),
                     sort_no_warning_first=True, top_k=top_k)


def find_compatible_cpus(main: dict, kb: pd.DataFrame, top_k: int = 10):
    main_socket = normalize_socket(_get_field(main, "socket", "socket_type", default=""))
    chip_code = extract_chipset_code(_get_field(main, "tên", "name", default=""))
    main_tier = chipset_tier(chip_code)

    def _check(cpu):
        cpu_socket = normalize_socket(_get_field(cpu, "socket", default=""))
        socket_match = bool(cpu_socket) and cpu_socket == main_socket
        
        cpu_p = parse_cpu_profile(_get_field(cpu, "tên", "name", default=""))
        if cpu_p and "tier_rank" in cpu_p:
            cpu_tier = cpu_p["tier_rank"]
            required_tier = max(1, min(3, cpu_tier) - 1)
        else:
            cpu_tdp = float(_get_field(cpu, "tdp", default=0) or 0)
            required_tier = min(3, required_tier_for_tdp(cpu_tdp))

        tier_ok = main_tier is not None and main_tier >= required_tier
        ok = socket_match and tier_ok
        
        reasons = [f"Socket khớp ({cpu_socket}), Mainboard Tier {main_tier} đủ gánh CPU (yêu cầu Tier {required_tier})."] if ok else []
        return {"is_compatible": ok, "socket_match": socket_match, "main_tier": main_tier, "reasons": reasons}

    return _collect(kb, "CPU", _check, require_compatible=True, top_k=top_k)


def find_compatible_gpus_for_cpu(cpu: dict, kb: pd.DataFrame, top_k: int = 10):
    """Không lọc — ưu tiên GPU không cảnh báo, rồi tier GẦN cpu_tier nhất."""
    cpu_tier = (parse_cpu_profile(_get_field(cpu, "tên", "name", default="")) or {}).get("tier_rank")
    sort_key = (lambda r: (1 if r["compat"]["warning"] else 0,
                           abs((r["compat"]["gpu_tier"] or 99) - cpu_tier))) if cpu_tier is not None else None
    return _collect(kb, "GPU", lambda g: check_cpu_gpu_compat(cpu, g), sort_key=sort_key, top_k=top_k)


def find_compatible_cpus_for_gpu(gpu: dict, kb: pd.DataFrame, top_k: int = 10):
    gpu_tier = (parse_gpu_profile(_get_field(gpu, "chipset", "tên", "name", default="")) or {}).get("tier_rank")
    sort_key = (lambda r: (1 if r["compat"]["warning"] else 0,
                           abs((r["compat"]["cpu_tier"] or 99) - gpu_tier))) if gpu_tier is not None else None
    return _collect(kb, "CPU", lambda c: check_cpu_gpu_compat(c, gpu), sort_key=sort_key, top_k=top_k)


def find_compatible_build(have_type: str, have_item: dict, kb: pd.DataFrame, top_k: int = 5) -> Dict[str, Any]:
    have_type = have_type.lower()
    if have_type == "cpu":
        return {
            "mainboards": find_compatible_mainboards(have_item, kb, top_k),
            "gpus": find_compatible_gpus_for_cpu(have_item, kb, top_k),
        }
    if have_type == "mainboard":
        return {
            "cpus": find_compatible_cpus(have_item, kb, top_k),
            "gpus": find_compatible_gpus_for_main(have_item, kb, top_k),
        }
    if have_type == "gpu":
        return {
            "mainboards": find_compatible_mains_for_gpu(have_item, kb, top_k),
            "cpus": find_compatible_cpus_for_gpu(have_item, kb, top_k),
        }
    raise ValueError(f"have_type không hợp lệ: {have_type}. Phải là cpu/gpu/mainboard.")
