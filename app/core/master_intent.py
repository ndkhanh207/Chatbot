import ollama
import re
from pydantic import BaseModel, Field, model_validator
from typing import Literal

from app.utils.model_utils import get_ollama_model
from app.core.prompts import (
    _SYSTEM_CLASSIFY,
    _FEWSHOT_CLASSIFY,
    _SYSTEM_EXTRACT,
    _FEWSHOT_BY_INTENT,
    _FALLBACK_MAP
)

# ==============================================================================
# CONSTANTS & CONFIG
# ==============================================================================

MAX_TOKENS_CLASSIFY = 100
MAX_TOKENS_EXTRACT = 250
MAX_HISTORY_MSGS = 4
MAX_HISTORY_CHAR_LIMIT = 200

COMPAT_TRIGGERS = [
    'lắp với', 'đi với', 'tương thích', 'lắp được', 'chạy được', 'hợp không',
    'đi cùng', 'vừa không', 'cắm được', 'gắn được', 'kết hợp', 'có ổn không',
    'có sao không', 'phối với', 'ghép với', 'chạy chung'
]

CPU_REGEX = r'(amd ryzen\s*[3579]\s+\d{4,5}[a-z0-9]*|intel core i[3579][-\s]?\d{4,5}[a-z0-9]*|ryzen\s*[3579]\s+\d{4,5}[a-z0-9]*|i[3579][-\s]?\d{4,5}[a-z0-9]*|ryzen\s+[3579])'
GPU_REGEX = r'((?:geforce\s+)?(?:rtx|gtx)\s*\d{3,4}(?:\s*ti|\s*super)?(?:\s*gaming)?(?:\s*\d{1,2}g)?|radeon\s+rx\s*\d{3,4}(?:\s*xt)?|rx\s*\d{3,4}(?:\s*xt)?)'
MAIN_REGEX = r'(asus\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|gigabyte\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|msi\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|asrock\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|mainboard\s+[a-z0-9-]+|main\s+[a-z0-9-]+)'

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
        "build_pc",           # Tư vấn/lắp BỘ PC TRỌN BỘ (CPU+GPU+Mainboard)
        "general_search",     # Tìm linh kiện chung chung (không kèm giá/thông số)
        "none"                # Giao tiếp thông thường / Không rõ
    ] = "none"

class MasterIntentSchema(BaseModel):
    reasoning: str = Field(description="Bước 1: Trích dẫn NGUYÊN VĂN tên linh kiện. Bước 2: Phân tích ý định.")
    intent: str = "none" # Gán lại từ Pass 1, LLM Pass 2 cũng output lại
    
    target_product: str = Field(
        default="none", 
        description="Tên linh kiện chính khi ý định là 'specification' hoặc 'price_check' (VD: 'i9 14900k', 'rtx 4060'). Mặc định 'none'."
    )
    spec_detail: str = Field(
        default="none", 
        description="Từ khóa thông số khách hỏi (vd: 'lõi', 'vram', 'socket', 'xung tối đa'). Nếu hỏi chung chung điền 'all'. Mặc định 'none'."
    )
    cpu: str = Field(default="none", description="LUÔN trích xuất tên CPU nếu có trong câu (VD: 'i9 14900k', 'ryzen 7 9800x3d'). Mặc định 'none'.")
    mainboard: str = Field(default="none", description="LUÔN trích xuất tên Mainboard nếu có trong câu (VD: 'asus b760m', 'msi b850 pro'). Mặc định 'none'.")
    gpu: str = Field(default="none", description="LUÔN trích xuất tên GPU/VGA nếu có trong câu (VD: 'rtx 5070 ti', 'rx 7900 xt'). Mặc định 'none'.")
    budget_amount: int = 0        # (VD: 4000000)
    category: str = Field(
        default="none",
        description="Loại linh kiện khách đang tìm kiếm (vd: 'gpu', 'mainboard', 'cpu'). CẤM TUYỆT ĐỐI điền 'price', 'giá', 'specification'."
    )

    @model_validator(mode='after')
    def auto_fix_target_product(self) -> 'MasterIntentSchema':
        # Nếu là hỏi thông số/giá mà target_product bị trống (bị LLM điền chữ none)
        if self.intent in ["specification", "price_check"] and self.target_product == "none":
            for field_value in [self.cpu, self.gpu, self.mainboard]:
                if field_value != "none":
                    self.target_product = field_value
                    break
                    
        # Tự động dọn rác nếu LLM vẫn cố chấp điền "price" vào category
        invalid_words = ["price", "specification", "info", "none", "giá", "thông số"]
        if self.category.lower() in invalid_words:
            if self.cpu != "none": self.category = "cpu"
            elif self.mainboard != "none": self.category = "mainboard"
            elif self.gpu != "none": self.category = "gpu"
            else: self.category = "none"
        return self


# ==============================================================================
# PIPELINE HELPER FUNCTIONS
# ==============================================================================

def _build_history_context(chat_history: list = None) -> str:
    if not chat_history:
        return ""
    
    context = "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\n"
    for msg in chat_history[-MAX_HISTORY_MSGS:]:
        role = "Khách" if getattr(msg, "type", "") == "human" else "AI"
        content = msg.content
        if role == "AI" and len(content) > MAX_HISTORY_CHAR_LIMIT:
            content = content[:MAX_HISTORY_CHAR_LIMIT] + "..."
        context += f"{role}: {content}\n"
    return context + "\n"

def _count_components(msg_l: str) -> tuple:
    cpu_match = re.search(CPU_REGEX, msg_l)
    gpu_match = re.search(GPU_REGEX, msg_l)
    main_match = re.search(MAIN_REGEX, msg_l)
    comp_count = sum(1 for x in [cpu_match, gpu_match, main_match] if x)
    return comp_count, cpu_match, gpu_match, main_match

def _apply_pre_extraction_guards(msg_l: str, comp_count: int, intent_pass1: str) -> str:
    has_compat_trigger = any(t in msg_l for t in COMPAT_TRIGGERS)
    if has_compat_trigger and comp_count >= 2 and intent_pass1 != "compatibility":
        print(f"\u26a0\ufe0f [GUARD] Pass 1 phân loại nhầm ({intent_pass1}). Ép thành 'compatibility'.")
        return "compatibility"
    return intent_pass1

def _apply_post_extraction_guards(parsed: MasterIntentSchema, cpu_match, gpu_match, main_match, comp_count: int):
    # Tách gộp target_product
    if parsed.target_product and parsed.target_product.lower() != "none":
        tp_lower = parsed.target_product.lower()
        tp_comp_count = sum(1 for match in [cpu_match, gpu_match, main_match] if match and match.group(1) in tp_lower)
        
        if tp_comp_count >= 2:
            print(f"[INTENT-GUARD] Tách entity từ target_product bị gộp: '{parsed.target_product}'")
            if cpu_match and cpu_match.group(1) in tp_lower and parsed.cpu == "none":
                parsed.cpu = cpu_match.group(1)
            if gpu_match and gpu_match.group(1) in tp_lower and parsed.gpu == "none":
                parsed.gpu = gpu_match.group(1)
            if main_match and main_match.group(1) in tp_lower and parsed.mainboard == "none":
                parsed.mainboard = main_match.group(1)
            parsed.target_product = "none"

    # Regex Rescue
    if parsed.intent == "compatibility" and comp_count >= 2:
        if parsed.cpu == "none" and cpu_match: parsed.cpu = cpu_match.group(1)
        if parsed.gpu == "none" and gpu_match: parsed.gpu = gpu_match.group(1)
        if parsed.mainboard == "none" and main_match: parsed.mainboard = main_match.group(1)

def _check_retry_condition(parsed: MasterIntentSchema) -> str | None:
    named_items = [parsed.cpu, parsed.mainboard, parsed.gpu]
    valid_named = [i for i in named_items if i and i.strip().lower() != "none"]
    has_target = parsed.target_product and parsed.target_product.strip().lower() != "none"
    
    if parsed.intent == "compatibility":
        total_items = len(valid_named) + (1 if has_target else 0)
        if total_items <= 1:
            return "suggestion"
            
    elif parsed.intent == "price_calculation":
        total_items = len(valid_named) + (1 if has_target and not valid_named else 0)
        if total_items <= 1:
            return "price_check"
            
    return None

def _handle_retry(user_msg: str, history_context: str, parsed: MasterIntentSchema, fallback_intent: str) -> MasterIntentSchema:
    print(f"\u26a0\ufe0f [RETRY] Guard detected mismatch ({parsed.intent} \u2192 {fallback_intent}). Retrying Pass 2...")
    new_parsed = _run_extraction_pass(user_msg, fallback_intent, history_context)
    new_parsed.intent = fallback_intent
    
    if fallback_intent == "suggestion" and new_parsed.target_product != "none":
        tp = new_parsed.target_product.lower()
        if any(k in tp for k in ["ryzen", "i3", "i5", "i7", "i9", "core", "cpu", "chip"]): 
            new_parsed.cpu = new_parsed.target_product
        elif any(k in tp for k in ["rtx", "gtx", "rx ", "radeon", "geforce"]): 
            new_parsed.gpu = new_parsed.target_product
        else: 
            new_parsed.cpu = new_parsed.target_product
        new_parsed.target_product = "none"
        
    return new_parsed


# ==============================================================================
# PIPELINE EXECUTION
# ==============================================================================

def _run_classification_pass(user_msg: str, history_context: str) -> str:
    """Pass 1: Phân loại Intent"""
    messages = (
        [{"role": "system", "content": _SYSTEM_CLASSIFY}]
        + _FEWSHOT_CLASSIFY
        + [{"role": "user", "content": f"{history_context}<user_input>{user_msg}</user_input>"}]
    )
    response = ollama.chat(
        model=get_ollama_model(),
        messages=messages,
        options={"temperature": 0.0, "num_predict": MAX_TOKENS_CLASSIFY},
        format=IntentOnlySchema.model_json_schema(),
    )
    raw = response["message"]["content"].strip()
    if not raw.endswith('}'): raw += '}'
    print(f"\n\U0001f50d [PASS-1] Raw: {raw}")
    try:
        return IntentOnlySchema.model_validate_json(raw).intent
    except:
        return "none"


def _run_extraction_pass(user_msg: str, intent: str, history_context: str) -> MasterIntentSchema:
    """Pass 2: Trích xuất Entity"""
    fewshots = _FEWSHOT_BY_INTENT.get(intent, _FEWSHOT_BY_INTENT["none"])
    prompt_msg = f"{history_context}<system_hint>Intent = {intent}</system_hint>\n<user_input>{user_msg}</user_input>"
    
    messages = (
        [{"role": "system", "content": _SYSTEM_EXTRACT}]
        + fewshots
        + [{"role": "user", "content": prompt_msg}]
    )
    response = ollama.chat(
        model=get_ollama_model(),
        messages=messages,
        options={"temperature": 0.0, "num_predict": MAX_TOKENS_EXTRACT},
        format=MasterIntentSchema.model_json_schema(),
    )
    raw = response["message"]["content"].strip()
    if not raw.endswith('}'): raw += '}'
    print(f"\U0001f50d [PASS-2] Raw ({intent}): {raw}")
    return MasterIntentSchema.model_validate_json(raw)


def parse_master_intent(user_msg: str, chat_history: list = None) -> MasterIntentSchema:
    """
    Bóc tách tên linh kiện + ý định bằng LLM 2-Stage Pipeline.
    Orchestrates Pass 1, Pre-Guards, Pass 2, Post-Guards, and Retry Logic.
    """
    history_context = _build_history_context(chat_history)

    try:
        # 1. PASS 1
        intent_pass1 = _run_classification_pass(user_msg, history_context)
        
        # 2. Pre-extraction Guards
        msg_l = user_msg.lower()
        comp_count, cpu_match, gpu_match, main_match = _count_components(msg_l)
        intent_pass1 = _apply_pre_extraction_guards(msg_l, comp_count, intent_pass1)
            
        # 3. PASS 2
        parsed = _run_extraction_pass(user_msg, intent_pass1, history_context)
        parsed.intent = intent_pass1 
        
        # 4. Post-extraction Guards
        _apply_post_extraction_guards(parsed, cpu_match, gpu_match, main_match, comp_count)

        # 5. Retry Logic
        fallback_intent = _check_retry_condition(parsed)
        if fallback_intent:
            parsed = _handle_retry(user_msg, history_context, parsed, fallback_intent)

        return parsed
        
    except Exception as e:
        print(f"\u274c [INTENT-LLM] Lỗi parse intent, fallback 'none': {e}")
        return MasterIntentSchema(
            reasoning="Fallback do lỗi kết nối LLM",
            intent="none", target_product="none", spec_detail="none",
            cpu="none", mainboard="none", gpu="none", budget_amount=0, category="none"
        )