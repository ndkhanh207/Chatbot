import ollama
import re
from time import perf_counter
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from typing import Literal

from config.config import Config
from app.utils.model_utils import get_ollama_model, log_ollama_metrics
from app.core.intent.prompts import (
    _SYSTEM_CLASSIFY,
    _FEWSHOT_CLASSIFY,
    _SYSTEM_EXTRACT,
    _FEWSHOT_BY_INTENT,
)
from app.core.intent.history_context import build_history_context, extract_structured_state
from app.specification.field_resolver import resolve_explicit_spec_detail
BUILD_KEYWORDS = [
    "build pc", "build máy", "build", "ráp pc", "lắp pc", "ráp máy", "lắp máy", "cấu hình", "dàn máy", "mua máy",
    "bộ pc", "máy tính bàn", "desktop", "tư vấn pc", "tư vấn máy", "gợi ý pc", "máy tính", "bộ máy", "thùng máy"
]

def detect_build_pc_intent(msg: str) -> bool:
    msg_l = msg.lower()
    return any(kw in msg_l for kw in BUILD_KEYWORDS)

# ==============================================================================
# CONSTANTS & CONFIG
# ==============================================================================

# ==============================================================================
# CONSTANTS & CONFIG
# ==============================================================================

MAX_TOKENS_CLASSIFY = 100
MAX_TOKENS_EXTRACT = 512

def _get_async_client():
    return ollama.AsyncClient(timeout=Config.OLLAMA_REQUEST_TIMEOUT)

COMPAT_TRIGGERS = [
    'lắp với', 'đi với', 'tương thích', 'lắp được', 'chạy được', 'hợp không',
    'đi cùng', 'vừa không', 'cắm được', 'gắn được', 'kết hợp', 'có ổn không',
    'có sao không', 'phối với', 'ghép với', 'chạy chung'
]

REVIEW_TRIGGERS = [
    'đánh giá', 'nhận xét', 'review', 'ổn không', 'tốt không', 'nghẽn', 
    'bottleneck', 'cân bằng', 'đáng mua', 'chấm điểm'
]

SPEC_TRIGGERS = [
    'vram', 'xung', 'socket', 'lõi', 'nhân', 'tdp', 'bộ nhớ', 'thông số',
    'mượt', 'khỏe', 'băng thông', 'tốc độ', 'chuẩn', 'giao tiếp', 'kích cỡ',
    'kích thước', 'chiều dài', 'dài bao nhiêu', 'màu', 'watt', 'điện năng',
    'công suất', 'chạy ở', 'gb ram', 'khe cắm', 'ram', 'ddr4', 'ddr5',
    'hỗ trợ', 'loại'
]

FOLLOW_UP_MARKERS = ['vậy', 'thì sao', 'thế còn', 'còn', 'nó', 'của']
PRICE_TRIGGERS = ['giá', 'bao nhiêu tiền', 'nhiêu tiền']
BUDGET_TRIGGERS = ['triệu', 'tr', 'tầm', 'khoảng', 'dưới', 'trên']
CPU_PATTERN = re.compile(r'(amd ryzen\s*[3579]\s+\d{4,5}[a-z0-9]*|intel core i[3579][-\s]?\d{4,5}[a-z0-9]*|ryzen\s*[3579]\s+\d{4,5}[a-z0-9]*|i[3579][-\s]?\d{4,5}[a-z0-9]*|ryzen\s+[3579])', re.IGNORECASE)
GPU_PATTERN = re.compile(r'((?:(?:asus|msi|gigabyte|galax|sapphire|powercolor|asrock|zotac|evga|palit|inno3d)\s+(?:\w+\s+){0,4})?(?:geforce\s+)?(?:rtx|gtx)\s*\d{3,4}(?:\s*ti|\s*super)?(?:\s*(?:\d{1,2}gb?|\d{1,2}g|gddr\d+x?|black|white|oc|gaming|trio))*|radeon\s+rx\s*\d{3,4}(?:\s*xt)?|rx\s*\d{3,4}(?:\s*xt)?)', re.IGNORECASE)
MAIN_PATTERN = re.compile(r'(asus\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|gigabyte\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|msi\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|asrock\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|mainboard\s+(?!(?:asus|msi|gigabyte|asrock)\b)[a-z0-9-]+|main\s+(?!(?:asus|msi|gigabyte|asrock)\b)[a-z0-9-]+)', re.IGNORECASE)

# ==============================================================================
# SCHEMAS
# ==============================================================================

class IntentOnlySchema(BaseModel):
    intent: Literal[
        "compatibility",      # 2 linh kiện có hợp nhau không?
        "suggestion",         # Có 1 món, tìm món còn lại ghép vào
        "price_calculation",  # Tính tổng tiền nhiều món
        "specification",      # Hỏi thông số của 1 món cụ thể (vd: vram, socket)
        "price_check",        # Hỏi giá của 1 món cụ thể
        "budget_search",      # Tìm 1 linh kiện đơn lẻ theo ngân sách tối đa
        "combo_review",       # Đánh giá combo CPU + GPU + Mainboard có sẵn
        "build_pc",           # Tư vấn/lắp BỘ PC TRỌN BỘ (CPU+GPU+Mainboard)
        "general_search",     # Tìm linh kiện chung chung (không kèm giá/thông số)
        "none"                # Giao tiếp thông thường / Không rõ
    ] = "none"

class MasterIntentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = "none" # Gán lại từ Pass 1, LLM Pass 2 cũng output lại
    
    target_product: str | None = Field(
        default=None,
        description="Tên linh kiện chính xuất hiện trong câu hiện tại khi intent là specification hoặc price_check.",
    )
    spec_detail: str | None = Field(
        default=None,
        description="Từ khóa thông số xuất hiện trong câu hiện tại (vd: lõi, vram, socket, xung tối đa).",
    )
    cpu: str | None = Field(default=None, description="Tên CPU xuất hiện trong câu hiện tại.")
    mainboard: str | None = Field(default=None, description="Tên mainboard xuất hiện trong câu hiện tại.")
    gpu: str | None = Field(default=None, description="Tên GPU/VGA xuất hiện trong câu hiện tại.")
    budget_amount: int = Field(
        default=0,
        description="Ngân sách khách yêu cầu. BẮT BUỘC CHUYỂN ĐỔI thành số nguyên VNĐ. Ví dụ: '20 triệu', '20tr', 'tầm 20' → 20000000. '500k' → 500000. Mặc định 0."
    )
    category: str | None = Field(
        default=None,
        description="Loại linh kiện khách đang tìm kiếm (vd: 'gpu', 'mainboard', 'cpu'). CẤM TUYỆT ĐỐI điền 'price', 'giá', 'specification'."
    )

    @field_validator("target_product", "spec_detail", "cpu", "mainboard", "gpu", "category", mode="before")
    @classmethod
    def normalize_missing_text(cls, value):
        if value is None or (isinstance(value, str) and value.strip().lower() in {"", "none"}):
            return None
        return value

    @model_validator(mode='after')
    def auto_fix_target_product(self) -> 'MasterIntentSchema':
        # Nếu là hỏi thông số/giá mà target_product bị trống (bị LLM điền chữ none)
        if self.intent in ["specification", "price_check"] and not self.target_product:
            for field_value in [self.cpu, self.gpu, self.mainboard]:
                if field_value:
                    self.target_product = field_value
                    break
                    
        # Tự động dọn rác nếu LLM vẫn cố chấp điền "price" vào category
        invalid_words = ["price", "specification", "info", "giá", "thông số"]
        if self.category and self.category.lower() in invalid_words:
            if self.cpu: self.category = "cpu"
            elif self.mainboard: self.category = "mainboard"
            elif self.gpu: self.category = "gpu"
            else: self.category = None
        return self


# ==============================================================================
# PIPELINE HELPER FUNCTIONS
# ==============================================================================

def _count_components(msg_l: str) -> tuple:
    cpu_match = CPU_PATTERN.search(msg_l)
    gpu_match = GPU_PATTERN.search(msg_l)
    main_match = MAIN_PATTERN.search(msg_l)
    comp_count = sum(1 for x in [cpu_match, gpu_match, main_match] if x)
    return comp_count, cpu_match, gpu_match, main_match

def _has_explicit_build(msg: str) -> bool:
    return detect_build_pc_intent(msg)

def _apply_pre_extraction_guards(
    msg_l: str,
    comp_count: int,
    intent_pass1: str,
    structured_state: dict,
) -> str:
    has_compat_trigger = any(t in msg_l for t in COMPAT_TRIGGERS)
    has_review_trigger = any(t in msg_l for t in REVIEW_TRIGGERS)
    has_budget_trigger = any(t in msg_l for t in BUDGET_TRIGGERS)
    is_explicit_build = _has_explicit_build(msg_l)
    last_intent = str(structured_state.get("last_intent") or "none").lower()
    category = str(structured_state.get("category") or "none").lower()

    if has_compat_trigger and comp_count >= 2 and intent_pass1 != "compatibility":
        print(f"⚠️ [GUARD] Pass 1 phân loại nhầm ({intent_pass1}). Ép thành 'compatibility'.")
        return "compatibility"

    has_full_combo = structured_state.get("cpu", "none") != "none" and structured_state.get("gpu", "none") != "none" and structured_state.get("mainboard", "none") != "none"
    if has_review_trigger and (comp_count >= 3 or has_full_combo):
        print(f"⚠️ [GUARD] Phát hiện từ khóa review + có đủ combo. Ép thành 'combo_review'.")
        return "combo_review"

    has_spec_trigger = any(t in msg_l for t in SPEC_TRIGGERS)
    if has_spec_trigger and intent_pass1 not in ["specification", "combo_review"] and not (
        intent_pass1 == "compatibility" and comp_count >= 2
    ):
        is_follow_up = any(t in msg_l for t in FOLLOW_UP_MARKERS)
        has_state_component = any(
            structured_state.get(k, "none") != "none"
            for k in ["cpu", "gpu", "mainboard", "target_product"]
        )
        if comp_count >= 1 or (is_follow_up and has_state_component):
            print(f"⚠️ [GUARD] Phát hiện từ khóa thông số/chuẩn giao tiếp. Ép thành 'specification'.")
            return "specification"

    if intent_pass1 == "build_pc" and has_budget_trigger and not is_explicit_build:
        if category != "none" and last_intent != "build_pc":
            print("⚠️ [GUARD] Budget follow-up theo danh mục. Ép thành 'budget_search'.")
            return "budget_search"

    is_follow_up = any(t in msg_l for t in FOLLOW_UP_MARKERS)
    has_explicit_new_intent = (
        has_compat_trigger
        or has_spec_trigger
        or any(t in msg_l for t in PRICE_TRIGGERS)
        or has_budget_trigger
        or is_explicit_build
    )
    if is_follow_up and not has_explicit_new_intent:
        if last_intent != "none":
            print(f"⚠️ [GUARD] Câu hỏi nối tiếp mơ hồ. Ép kế thừa intent: {last_intent}")
            return last_intent

    # Nếu nhắc đích danh linh kiện cụ thể (comp_count >= 1) thì không thể là tìm kiếm chung chung.
    if comp_count >= 1 and intent_pass1 in ["general_search", "none"]:
        if last_intent not in ["general_search", "none"]:
            print(f"\u26a0\ufe0f [GUARD] Nhắc tên linh kiện cụ thể nhưng Pass 1 trả {intent_pass1}. Ép kế thừa: {last_intent}")
            return last_intent
        print(f"\u26a0\ufe0f [GUARD] Nhắc tên linh kiện cụ thể nhưng Pass 1 trả {intent_pass1}. Mặc định ép về price_check")
        return "price_check"

    return intent_pass1

def _apply_post_extraction_guards(parsed: MasterIntentSchema, cpu_match, gpu_match, main_match, comp_count: int):
    # Tách gộp target_product
    if parsed.target_product:
        tp_lower = parsed.target_product.lower()
        tp_comp_count = sum(1 for match in [cpu_match, gpu_match, main_match] if match and match.group(1) in tp_lower)
        
        if tp_comp_count >= 2:
            print(f"[INTENT-GUARD] Tách entity từ target_product bị gộp: '{parsed.target_product}'")
            if cpu_match and cpu_match.group(1) in tp_lower and not parsed.cpu:
                parsed.cpu = cpu_match.group(1)
            if gpu_match and gpu_match.group(1) in tp_lower and not parsed.gpu:
                parsed.gpu = gpu_match.group(1)
            if main_match and main_match.group(1) in tp_lower and not parsed.mainboard:
                parsed.mainboard = main_match.group(1)
            parsed.target_product = None

    # Explicit entities in current message always replace copied/history values.
    if cpu_match:
        parsed.cpu = cpu_match.group(1)
    if gpu_match:
        parsed.gpu = gpu_match.group(1)
    if main_match:
        parsed.mainboard = main_match.group(1)

    if parsed.intent in ["specification", "price_check"]:
        explicit_components = [
            (cpu_match, "cpu"),
            (gpu_match, "gpu"),
            (main_match, "mainboard"),
        ]
        for match, category in explicit_components:
            if match:
                parsed.target_product = match.group(1)
                parsed.category = category
                if category != "cpu":
                    parsed.cpu = None
                if category != "gpu":
                    parsed.gpu = None
                if category != "mainboard":
                    parsed.mainboard = None
                break

    # Sửa lỗi LLM điền sai slot (vd: rx 7600 bị nhét vào slot CPU)
    if parsed.cpu and GPU_PATTERN.search(parsed.cpu):
        parsed.gpu = parsed.cpu
        parsed.cpu = None
        if parsed.category == "cpu": parsed.category = "gpu"
    elif parsed.gpu and CPU_PATTERN.search(parsed.gpu):
        parsed.cpu = parsed.gpu
        parsed.gpu = None
        if parsed.category == "gpu": parsed.category = "cpu"

    if parsed.intent in ["specification", "price_check"] and not parsed.target_product:
        for field_value in [parsed.cpu, parsed.gpu, parsed.mainboard]:
            if field_value:
                parsed.target_product = field_value
                break


def _pick_state_component(parsed: MasterIntentSchema, state: dict) -> str | None:
    category = (parsed.category or "").lower()
    target = (parsed.target_product or "").lower()
    spec = (parsed.spec_detail or "").lower()
    text = f"{category} {target} {spec}"

    if any(k in text for k in ["gpu", "vga", "card", "rtx", "gtx", "rx"]):
        return state.get("gpu")
    if any(k in text for k in ["main", "mainboard", "bo mach", "motherboard", "socket"]):
        return state.get("mainboard")
    if any(k in text for k in ["cpu", "core", "loi", "nhan", "i3", "i5", "i7", "i9", "ryzen"]):
        return state.get("cpu")
    return state.get("target_product") or state.get("cpu") or state.get("gpu") or state.get("mainboard")


def _normalize_single_product_category(parsed: MasterIntentSchema) -> None:
    if parsed.intent not in ["specification", "price_check"]:
        return

    target = (parsed.target_product or "").lower()
    if GPU_PATTERN.search(target):
        parsed.category = "gpu"
        parsed.gpu = parsed.target_product
        parsed.cpu = parsed.mainboard = None
    elif CPU_PATTERN.search(target):
        parsed.category = "cpu"
        parsed.cpu = parsed.target_product
        parsed.gpu = parsed.mainboard = None
    elif MAIN_PATTERN.search(target):
        parsed.category = "mainboard"
        parsed.mainboard = parsed.target_product
        parsed.cpu = parsed.gpu = None


def _inherit_structured_followup_state(parsed: MasterIntentSchema, state: dict, cpu_match, gpu_match, main_match, msg_l: str):
    stateful_intents = {
        "specification", "price_check", "compatibility", "suggestion",
        "combo_review", "general_search", "budget_search",
    }
    if parsed.intent not in stateful_intents:
        return

    if not parsed.category and state.get("category"):
        parsed.category = state["category"]

    if parsed.intent not in ["specification", "price_check", "compatibility", "suggestion", "combo_review"]:
        return

    force_verified_state = parsed.intent in ["compatibility", "suggestion", "combo_review"]

    if not cpu_match and state.get("cpu") and (not parsed.cpu or force_verified_state):
        parsed.cpu = state["cpu"]
    if not gpu_match and state.get("gpu") and (not parsed.gpu or force_verified_state):
        parsed.gpu = state["gpu"]
    if not main_match and state.get("mainboard") and (not parsed.mainboard or force_verified_state):
        parsed.mainboard = state["mainboard"]

    if parsed.intent in ["specification", "price_check"] and not any([cpu_match, gpu_match, main_match]):
        inherited = state.get("target_product") or _pick_state_component(parsed, state)
        if inherited:
            parsed.target_product = inherited

    if parsed.intent == "specification":
        explicit_spec_detail = resolve_explicit_spec_detail(msg_l)
        if explicit_spec_detail:
            parsed.spec_detail = explicit_spec_detail
        elif state.get("spec_detail"):
            parsed.spec_detail = state["spec_detail"]

    _normalize_single_product_category(parsed)

def _check_retry_condition(parsed: MasterIntentSchema) -> str | None:
    products = {
        re.sub(r"[\s-]+", " ", item.strip().lower())
        for item in [parsed.cpu, parsed.mainboard, parsed.gpu, parsed.target_product]
        if item
    }
    
    if parsed.intent == "compatibility":
        if len(products) <= 1:
            return "suggestion"
            
    elif parsed.intent == "price_calculation":
        if len(products) <= 1:
            return "price_check"
            
    return None

async def _handle_retry(user_msg: str, parsed: MasterIntentSchema, fallback_intent: str) -> MasterIntentSchema:
    print(f"\u26a0\ufe0f [RETRY] Guard detected mismatch ({parsed.intent} \u2192 {fallback_intent}). Retrying Pass 2...")
    new_parsed = await _run_extraction_pass(user_msg, fallback_intent)
    new_parsed.intent = fallback_intent
    
    if fallback_intent == "suggestion" and new_parsed.target_product:
        tp = new_parsed.target_product.lower()
        if any(k in tp for k in ["ryzen", "i3", "i5", "i7", "i9", "core", "cpu", "chip"]): 
            new_parsed.cpu = new_parsed.target_product
        elif any(k in tp for k in ["rtx", "gtx", "rx ", "radeon", "geforce"]): 
            new_parsed.gpu = new_parsed.target_product
        else: 
            new_parsed.cpu = new_parsed.target_product
        new_parsed.target_product = None
        
    return new_parsed


# ==============================================================================
# PIPELINE EXECUTION
# ==============================================================================


async def _run_classification_pass(user_msg: str, history_context: str) -> str:
    """Pass 1: Phân loại Intent"""
    messages = (
        [{"role": "system", "content": _SYSTEM_CLASSIFY}]
        + _FEWSHOT_CLASSIFY
        + [{"role": "user", "content": f"{history_context}<user_input>{user_msg}</user_input>"}]
    )
    started = perf_counter()
    response = await _get_async_client().chat(
        model=get_ollama_model(),
        messages=messages,
        options={"temperature": 0.0, "num_predict": MAX_TOKENS_CLASSIFY},
        format=IntentOnlySchema.model_json_schema(),
    )
    log_ollama_metrics("intent_classify", response, perf_counter() - started)
    raw = response["message"]["content"].strip()
    if not raw.endswith('}'): raw += '}'
    print(f"\n\U0001f50d [PASS-1] Raw: {raw}")
    try:
        return IntentOnlySchema.model_validate_json(raw).intent
    except ValidationError as e:
        print(f"\u26a0\ufe0f [PASS-1] Lỗi parse JSON intent ({e}). Fallback 'none'.")
        return "none"


async def _run_extraction_pass(user_msg: str, intent: str) -> MasterIntentSchema:
    """Pass 2: Trích xuất Entity"""
    fewshots = _FEWSHOT_BY_INTENT.get(intent, _FEWSHOT_BY_INTENT["none"])
    prompt_msg = f"<system_hint>Intent = {intent}</system_hint>\n<user_input>{user_msg}</user_input>"
    
    messages = (
        [{"role": "system", "content": _SYSTEM_EXTRACT}]
        + fewshots
        + [{"role": "user", "content": prompt_msg}]
    )
    started = perf_counter()
    response = await _get_async_client().chat(
        model=get_ollama_model(),
        messages=messages,
        options={"temperature": 0.0, "num_predict": MAX_TOKENS_EXTRACT},
        format=MasterIntentSchema.model_json_schema(),
    )
    log_ollama_metrics("intent_extract", response, perf_counter() - started)
    raw = response["message"]["content"].strip()
    if not raw.endswith('}'): raw += '}'
    print(f"\U0001f50d [PASS-2] Raw ({intent}): {raw}")
    return MasterIntentSchema.model_validate_json(raw)


async def parse_master_intent(user_msg: str, chat_history: list | None = None) -> MasterIntentSchema:
    """
    Bóc tách tên linh kiện + ý định bằng LLM 2-Stage Pipeline.
    Orchestrates Pass 1, Pre-Guards, Pass 2, Post-Guards, and Retry Logic.
    """
    if chat_history is None:
        chat_history = []
    history_context = build_history_context(chat_history)
    structured_state = extract_structured_state(chat_history)

    try:
        # Pre-extraction Guards
        msg_l = user_msg.lower()
        comp_count, cpu_match, gpu_match, main_match = _count_components(msg_l)

        # 0. FAST-PATH: Nếu có trigger rõ ràng + đủ số lượng linh kiện, bỏ qua luôn Pass 1 (tiết kiệm 1 lần gọi LLM)
        has_compat_trigger = any(t in msg_l for t in COMPAT_TRIGGERS)
        has_review_trigger = any(t in msg_l for t in REVIEW_TRIGGERS)
        has_budget_trigger = any(t in msg_l for t in BUDGET_TRIGGERS)
        is_explicit_build = _has_explicit_build(msg_l)
        has_price_trigger = any(t in msg_l for t in PRICE_TRIGGERS)
        has_full_combo = structured_state.get("cpu", "none") != "none" and structured_state.get("gpu", "none") != "none" and structured_state.get("mainboard", "none") != "none"

        intent_pass1 = "none"
        if has_compat_trigger and comp_count >= 2:
            intent_pass1 = "compatibility"
        elif has_review_trigger and (comp_count >= 3 or has_full_combo):
            intent_pass1 = "combo_review"
        elif is_explicit_build:
            intent_pass1 = "build_pc"
        elif ('tổng' in msg_l or 'cộng' in msg_l) and has_price_trigger and comp_count >= 2:
            intent_pass1 = "price_calculation"
        elif has_price_trigger and comp_count >= 1:
            intent_pass1 = "price_check"

        if intent_pass1 != "none":
            print(f"⚡ [FAST-PATH] Bỏ qua Pass 1 LLM, heuristic bắt được intent: {intent_pass1}")
        else:
            intent_pass1 = await _run_classification_pass(user_msg, history_context)

        # 2. Pre-extraction Guards (Vẫn chạy để vớt các trường hợp LLM Pass 1 phân loại sai)
        intent_pass1 = _apply_pre_extraction_guards(msg_l, comp_count, intent_pass1, structured_state)

        # PC Builder owns its own trained turn extraction. Running the generic
        # entity pass here would parse the same message twice.
        if intent_pass1 == "build_pc":
            return MasterIntentSchema(intent="build_pc")
            
        # 3. PASS 2
        parsed = await _run_extraction_pass(user_msg, intent_pass1)
        parsed.intent = intent_pass1 
        
        # 4. Post-extraction Guards
        _apply_post_extraction_guards(parsed, cpu_match, gpu_match, main_match, comp_count)
        _inherit_structured_followup_state(parsed, structured_state, cpu_match, gpu_match, main_match, msg_l)

        # 5. Retry Logic
        fallback_intent = _check_retry_condition(parsed)
        if fallback_intent:
            parsed = await _handle_retry(user_msg, parsed, fallback_intent)
            _apply_post_extraction_guards(parsed, cpu_match, gpu_match, main_match, comp_count)
            _inherit_structured_followup_state(parsed, structured_state, cpu_match, gpu_match, main_match, msg_l)

        return parsed
        
    except (ollama.RequestError, ollama.ResponseError, TimeoutError, ValidationError) as e:
        print(f"\u274c [INTENT-LLM] Lỗi parse intent, fallback 'none': {e}")
        return MasterIntentSchema(intent="none")
