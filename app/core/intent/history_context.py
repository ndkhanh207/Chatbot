import re

from app.memory.memory_store import normalize_context_metadata

MAX_HISTORY_MSGS = 4
MAX_HISTORY_CHAR_LIMIT = 200

# Shared component extraction. Keep this broad: DB lookup decides truth later.
CPU_RE = re.compile(r'\b(i[3579](?:[-\s]?\d{4,5}[a-z0-9]*)?|ryzen\s*[3579](?:\s*\d{3,5}[a-z0-9]*)?|core\s*ultra\s*\d+|x3d)\b', re.I)
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
    metadata = normalize_context_metadata(meta)
    state = {}
    mapping = {
        "cpu": ["cpu", "last_suggested_cpu"],
        "gpu": ["gpu", "last_suggested_gpu"],
        "mainboard": ["mainboard", "last_suggested_mainboard"],
        "target_product": ["target_product"],
        "category": ["category"],
        "spec_detail": ["spec_detail"],
        "last_intent": ["intent", "last_intent"],
        "build_id": ["build_id"],
        "pending_question": ["pending_question"],
    }

    for out_key, keys in mapping.items():
        for key in keys:
            value = _clean(metadata.get(key))
            if value:
                state[out_key] = value
                break
    required_components = metadata.get("required_components") or {}
    if isinstance(required_components, dict):
        for category in ("cpu", "gpu", "mainboard"):
            if category not in state and _clean(required_components.get(category)):
                state[category] = _clean(required_components[category])
    if metadata.get("budget"):
        state["budget"] = metadata["budget"]
    return state


def extract_structured_state(chat_history: list | None) -> dict:
    """Trusted follow-up state: human text plus AI metadata, never AI prose."""
    if not chat_history:
        return {}

    # The newest machine snapshot is canonical. Do not merge independent
    # entities from unrelated older turns into a synthetic combo.
    for msg in reversed(chat_history[-6:]):
        if getattr(msg, "type", "") != "ai":
            continue
        state = _intent_state_from_meta(getattr(msg, "additional_kwargs", {}) or {})
        if state:
            return state

    # Legacy fallback for rows without metadata: inspect only the newest user turn.
    latest_user = next(
        (msg for msg in reversed(chat_history) if getattr(msg, "type", "") == "human"),
        None,
    )
    if latest_user is None:
        return {}

    content = latest_user.content
    state = {}
    for key, match in (
        ("cpu", CPU_RE.search(content)),
        ("gpu", GPU_RE.search(content)),
        ("mainboard", MAIN_RE.search(content)),
        ("category", CAT_RE.search(content)),
    ):
        if match:
            value = match.group(1 if key in {"mainboard", "category"} else 0).strip()
            state[key] = value.lower() if key == "category" else value
    for pattern, intent_name in INTENT_PATTERNS:
        if pattern.search(content):
            state["last_intent"] = intent_name
            break

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
