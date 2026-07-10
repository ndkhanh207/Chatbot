import re

MAX_HISTORY_MSGS = 4
MAX_HISTORY_CHAR_LIMIT = 200

# Shared component extraction. Keep this broad: DB lookup decides truth later.
CPU_RE = re.compile(r'\b(i[3579](?:-?\d{4,5}[a-z0-9]*)?|ryzen\s*[3579](?:\s*\d{3,5}[a-z0-9]*)?|core\s*ultra\s*\d+|x3d)\b', re.I)
GPU_RE = re.compile(r'\b(?:(?:asus|msi|gigabyte|galax|sapphire|powercolor|asrock|zotac|evga|palit|inno3d)\s+(?:\w+\s+){0,4})?(?:geforce\s+)?(?:rtx|gtx|rx|arc)\s*\d{3,5}(?:\s*ti|\s*xt|\s*xtx|\s*gre|\s*super)?(?:\s*(?:\d{1,2}gb?|\d{1,2}g|gddr\d+x?|black|white|oc|gaming|trio))*\b', re.I)
MAIN_RE = re.compile(r'\b([bzhx]\d{2,3}m?(?:-[a-z0-9]+)?)\b', re.I)
CAT_RE = re.compile(r'\b(gpu|cpu|mainboard|main|card|vga)\b', re.I)

INTENT_PATTERNS = [
    (re.compile(r'compatible|compatibility|lap duoc|tuong thich|di voi|chay chung|hop khong|ket hop|gan duoc', re.I), "compatibility"),
    (re.compile(r'gia\s*bao nhieu|gia\s*nhieu|bao\s*nhieu\s*tien|price|how much', re.I), "price_check"),
    (re.compile(r'vram|xung|socket|loi|nhan|core|tdp|bo nho|thong so|spec|manh|khoe', re.I), "specification"),
    (re.compile(r'tim|goi y|de xuat|phu hop|recommend', re.I), "suggestion"),
    (re.compile(r'build|rap|tu van pc|cau hinh', re.I), "build_pc"),
]


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.lower() == "none":
        return None
    return value


def _intent_state_from_meta(meta: dict) -> dict:
    nested = meta.get("intent_state") or {}
    state = {}
    mapping = {
        "cpu": ["cpu", "last_suggested_cpu", "user_cpu"],
        "gpu": ["gpu", "last_suggested_gpu", "user_gpu"],
        "mainboard": ["mainboard", "last_suggested_mainboard", "user_mainboard"],
        "target_product": ["target_product"],
        "category": ["category"],
        "spec_detail": ["spec_detail"],
        "last_intent": ["intent", "last_intent"],
        "build_id": ["build_id"],
        "preset_id": ["preset_id"],
        "pending_question": ["pending_question"],
    }

    for out_key, keys in mapping.items():
        for key in keys:
            value = _clean(nested.get(key)) or _clean(meta.get(key))
            if value:
                state[out_key] = value
                break
    if meta.get("budget"):
        state["budget"] = meta["budget"]
    return state


def extract_structured_state(chat_history: list | None) -> dict:
    """Trusted follow-up state: human text plus AI metadata, never AI prose."""
    if not chat_history:
        return {}

    state = {}

    # 1. Newest user entities win.
    for msg in reversed(chat_history[-6:]):
        if getattr(msg, "type", "") != "human":
            continue
        content = msg.content
        cpu_m = CPU_RE.search(content)
        gpu_m = GPU_RE.search(content)
        main_m = MAIN_RE.search(content)
        cat_m = CAT_RE.search(content)
        if cpu_m:
            state.setdefault("cpu", cpu_m.group(0).strip())
        if gpu_m:
            state.setdefault("gpu", gpu_m.group(0).strip())
        if main_m:
            state.setdefault("mainboard", main_m.group(1).strip())
        if cat_m:
            state.setdefault("category", cat_m.group(1).lower().strip())
        if "last_intent" not in state:
            for pattern, intent_name in INTENT_PATTERNS:
                if pattern.search(content):
                    state["last_intent"] = intent_name
                    break

    # 2. Saved machine state fills gaps.
    for msg in reversed(chat_history[-6:]):
        if getattr(msg, "type", "") != "ai":
            continue
        for key, value in _intent_state_from_meta(getattr(msg, "additional_kwargs", {}) or {}).items():
            state.setdefault(key, value)

    return state


def _extract_verified_state(chat_history: list) -> str:
    state = extract_structured_state(chat_history)
    return ", ".join(f"{k.upper()}={v}" for k, v in state.items())


def build_intent_metadata(parsed_intent) -> dict:
    fields = {
        "intent": getattr(parsed_intent, "intent", None),
        "cpu": getattr(parsed_intent, "cpu", None),
        "gpu": getattr(parsed_intent, "gpu", None),
        "mainboard": getattr(parsed_intent, "mainboard", None),
        "target_product": getattr(parsed_intent, "target_product", None),
        "category": getattr(parsed_intent, "category", None),
        "spec_detail": getattr(parsed_intent, "spec_detail", None),
    }
    return {"intent_state": {k: v for k, v in fields.items() if _clean(v)}}


def build_history_context(chat_history: list = None) -> str:
    if not chat_history:
        return ""

    verified_state = _extract_verified_state(chat_history)
    context = ""
    if verified_state:
        context += f"[STRUCTURED_STATE]:\n{verified_state}\n\n"

    context += "RECENT_USER_MESSAGES:\n"
    human_msgs = [m for m in chat_history if getattr(m, "type", "") == "human"]
    for msg in human_msgs[-MAX_HISTORY_MSGS:]:
        content = msg.content
        if len(content) > MAX_HISTORY_CHAR_LIMIT:
            content = content[:MAX_HISTORY_CHAR_LIMIT] + "..."
        context += f"Khach: {content}\n"
    return context + "\n"
