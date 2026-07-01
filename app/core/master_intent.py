import ollama
import re
from pydantic import BaseModel, Field, model_validator
from typing import Literal

from app.utils.model_utils import get_ollama_model

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

    # valid model 
    @model_validator(mode='after')
    def auto_fix_target_product(self) -> 'MasterIntentSchema':
        # Nếu là hỏi thông số/giá mà target_product bị trống (bị LLM điền chữ none)
        if self.intent in ["specification", "price_check"] and self.target_product == "none":
            # Tự động quét xem LLM có lỡ điền tên vào cpu/gpu/mainboard không, có thì bốc lên luôn
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
# PASS 1: CLASSIFICATION (SYSTEM PROMPT & FEWSHOT)
# ==============================================================================

_SYSTEM_CLASSIFY = (
    "Bạn là MÁY PHÂN LOẠI Ý ĐỊNH (Intent Classifier) nội bộ, KHÔNG PHẢI CHATBOT GIAO TIẾP VỚI KHÁCH.\n"
    "Nhiệm vụ của bạn là đọc câu hỏi và trả về đúng 1 ý định (intent) duy nhất dựa vào các luật sau.\n"
    "LUẬT PHÂN LOẠI TUYỆT ĐỐI (Strict Intent Mapping):\n"
    "- 'compatibility': Khách hỏi về TƯƠNG THÍCH, ĐỘ HỢP NHAU (từ khóa: 'có lắp được với', 'đi với', 'chạy chung', 'tương thích không'). Nếu câu hỏi có chứa 2 LINH KIỆN CỤ THỂ TRỞ LÊN, ĐÓ TUYỆT ĐỐI LÀ 'compatibility', KHÔNG BAO GIỜ là 'specification'.\n"
    "- 'suggestion': Khách CHỈ CÓ SẴN 1 LINH KIỆN và nhờ tìm 1 linh kiện MỚI (chưa biết tên) để ghép cùng. CHỈ CÓ 1 linh kiện cụ thể xuất hiện.\n"
    "- 'price_calculation': Khách liệt kê nhiều linh kiện và muốn tính TỔNG GIÁ tiền.\n"
    "- 'specification': Khách hỏi về THÔNG SỐ (số nhân, VRAM, điện năng...) của ĐÚNG 1 LINH KIỆN DUY NHẤT. Nghiêm cấm dùng intent này nếu khách hỏi độ tương thích giữa 2 linh kiện.\n"
    "- 'price_check': Khách hỏi GIÁ BÁN của 1 linh kiện cụ thể.\n"
    "- 'budget_search': Khách tìm MỘT LINH KIỆN ĐƠN LẺ dựa trên NGÂN SÁCH/TẦM GIÁ.\n"
    "- 'build_pc': Khách muốn tư vấn/lắp ráp BỘ PC TRỌN BỘ gồm nhiều linh kiện.\n"
    "- 'general_search': Khách tìm kiếm, hỏi mua, hoặc nhờ tư vấn chung chung về một loại linh kiện/sản phẩm.\n"
    "- 'none': Khách giao tiếp thông thường, hoặc hỏi ngoài lề."
)

_FEWSHOT_CLASSIFY = [
    {"role": "user", "content": "Intel Core i9-14900K có lắp được với main MSI B850 PRO không"},
    {"role": "assistant", "content": '{"intent": "compatibility"}'},
    {"role": "user", "content": "tôi có cpu ryzen 9 9950x3d rồi, tìm gpu phù hợp"},
    {"role": "assistant", "content": '{"intent": "suggestion"}'},
    {"role": "user", "content": "tôi lấy main asus z790 và i9 14900k tổng bao nhiêu"},
    {"role": "assistant", "content": '{"intent": "price_calculation"}'},
    {"role": "user", "content": "con rtx 4060 ti có mấy gb vram vậy"},
    {"role": "assistant", "content": '{"intent": "specification"}'},
    {"role": "user", "content": "con vga rtx 4080 super giá nhiêu shop"},
    {"role": "assistant", "content": '{"intent": "price_check"}'},
    {"role": "user", "content": "tư vấn em con card đồ họa tầm 8 triệu"},
    {"role": "assistant", "content": '{"intent": "budget_search"}'},
    {"role": "user", "content": "build pc gaming tầm 30 triệu"},
    {"role": "assistant", "content": '{"intent": "build_pc"}'},
    {"role": "user", "content": "tìm cho tôi ssd của samsung"},
    {"role": "assistant", "content": '{"intent": "general_search"}'},
    {"role": "user", "content": "chào shop, bạn là bot à"},
    {"role": "assistant", "content": '{"intent": "none"}'}
]


# ==============================================================================
# PASS 2: EXTRACTION (SYSTEM PROMPT & FOCUSED FEWSHOTS)
# ==============================================================================

_SYSTEM_EXTRACT = (
    "Bạn là MÁY TRÍCH XUẤT THỰC THỂ (Entity Extractor) nội bộ. Ý định (intent) đã được phân loại.\n"
    "Nhiệm vụ của bạn là trích xuất CÁC THỰC THỂ từ câu hỏi của khách.\n\n"
    "QUY TẮC TRÍCH XUẤT THỰC THỂ:\n"
    "1. 'target_product': Tên linh kiện cụ thể khi ý định là 'specification' hoặc 'price_check'.\n"
    "2. 'cpu', 'mainboard', 'gpu': Trích xuất BẰNG HẾT các tên CỤ THỂ xuất hiện trong câu.\n"
    "3. 'spec_detail': Tên thông số khách muốn biết (nếu có).\n"
    "4. 'budget_amount': Nếu khách nói ngân sách, CHUYỂN ĐỔI thành số nguyên VNĐ. Mặc định là 0.\n"
    "5. 'category': Loại linh kiện khách đang tìm kiếm. CẤM điền 'price', 'giá'.\n"
    "CẢNH BÁO: TRÍCH XUẤT CHÍNH XÁC TỪ KHÓA CỦA KHÁCH. Không tự ý ghép thêm hãng nếu khách không viết.\n"
    "Điền 'none' hoặc 0 nếu không có thông tin."
)

_FEWSHOT_BY_INTENT = {
    "compatibility": [
        {"role": "user", "content": "Intel Core i9-14900K có lắp được với main MSI B850 PRO B850M-VC AM5 không"},
        {"role": "assistant", "content": '{"reasoning": "Có 2 linh kiện cụ thể -> compatibility.", "intent": "compatibility", "target_product": "none", "spec_detail": "none", "cpu": "intel core i9-14900k", "mainboard": "msi b850 pro b850m-vc am5", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "AMD Ryzen 7 9800X3D đi với GPU GIGABYTE GeForce RTX 5070 Ti GAMING 16G có ổn không"},
        {"role": "assistant", "content": '{"reasoning": "Có 2 linh kiện cụ thể -> compatibility.", "intent": "compatibility", "target_product": "none", "spec_detail": "none", "cpu": "amd ryzen 7 9800x3d", "mainboard": "none", "gpu": "gigabyte geforce rtx 5070 ti gaming 16g", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "CPU i9 14900k có lắp được với ryzen 7 9800x3d không"},
        {"role": "assistant", "content": '{"reasoning": "Tương thích 2 CPU -> logic vô lý.", "intent": "none", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "suggestion": [
        {"role": "user", "content": "tôi có cpu ryzen 9 9950x3d rồi, tìm gpu phù hợp"},
        {"role": "assistant", "content": '{"reasoning": "Đã có 1 linh kiện, tìm linh kiện khác -> suggestion.", "intent": "suggestion", "target_product": "none", "spec_detail": "none", "cpu": "ryzen 9 9950x3d", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "gpu"}'},
        {"role": "user", "content": "tìm giúp tôi bo mạch chủ phù hợp cho CPU AMD Ryzen 7 7700X"},
        {"role": "assistant", "content": '{"reasoning": "Đã có 1 linh kiện, tìm linh kiện khác -> suggestion.", "intent": "suggestion", "target_product": "none", "spec_detail": "none", "cpu": "amd ryzen 7 7700x", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "mainboard"}'},
    ],
    "price_calculation": [
        {"role": "user", "content": "tôi lấy main asus z790 và i9 14900k tổng bao nhiêu"},
        {"role": "assistant", "content": '{"reasoning": "Liệt kê nhiều linh kiện và hỏi tổng.", "intent": "price_calculation", "target_product": "none", "spec_detail": "none", "cpu": "i9 14900k", "mainboard": "asus z790", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "specification": [
        {"role": "user", "content": "con rtx 4060 ti có mấy gb vram vậy"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi thông số cụ thể của 1 linh kiện.", "intent": "specification", "target_product": "rtx 4060 ti", "spec_detail": "vram", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "số lõi của i9 14900K là bao nhiêu"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi thông số lõi.", "intent": "specification", "target_product": "i9 14900k", "spec_detail": "số lõi", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "price_check": [
        {"role": "user", "content": "con vga rtx 4080 super giá nhiêu shop"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi giá 1 linh kiện cụ thể.", "intent": "price_check", "target_product": "rtx 4080 super", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "budget_search": [
        {"role": "user", "content": "tư vấn em con card tầm 4 triệu"},
        {"role": "assistant", "content": '{"reasoning": "Tìm 1 linh kiện theo ngân sách.", "intent": "budget_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 4000000, "category": "gpu"}'},
    ],
    "build_pc": [
        {"role": "user", "content": "build pc gaming tầm 30 triệu"},
        {"role": "assistant", "content": '{"reasoning": "Tư vấn nguyên bộ máy.", "intent": "build_pc", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 30000000, "category": "none"}'},
    ],
    "general_search": [
        {"role": "user", "content": "tìm cho tôi ssd của samsung"},
        {"role": "assistant", "content": '{"reasoning": "Tìm kiếm chung chung.", "intent": "general_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "ssd"}'},
    ],
    "none": [
        {"role": "user", "content": "bạn là ai, bot à"},
        {"role": "assistant", "content": '{"reasoning": "Giao tiếp ngoài lề.", "intent": "none", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ]
}

_FALLBACK_MAP = {
    "specification": "compatibility",
    "build_pc": "compatibility",
    "compatibility": "suggestion",
    "price_calculation": "price_check"
}


# ==============================================================================
# PIPELINE EXECUTION
# ==============================================================================

def _run_classification_pass(user_msg: str, history_context: str) -> str:
    """Pass 1: Phân loại Intent (chỉ tốn ~380 tokens)"""
    messages = (
        [{"role": "system", "content": _SYSTEM_CLASSIFY}]
        + _FEWSHOT_CLASSIFY
        + [{"role": "user", "content": f"{history_context}<user_input>{user_msg}</user_input>"}]
    )
    response = ollama.chat(
        model=get_ollama_model(),
        messages=messages,
        options={"temperature": 0.0, "num_predict": 100},
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
    """Pass 2: Trích xuất Entity với Fewshot tập trung (~550 tokens)"""
    fewshots = _FEWSHOT_BY_INTENT.get(intent, _FEWSHOT_BY_INTENT["none"])
    
    # Bơm thêm gợi ý vào user_msg để Pass 2 biết Pass 1 đã chọn intent gì
    prompt_msg = f"{history_context}<system_hint>Intent = {intent}</system_hint>\n<user_input>{user_msg}</user_input>"
    
    messages = (
        [{"role": "system", "content": _SYSTEM_EXTRACT}]
        + fewshots
        + [{"role": "user", "content": prompt_msg}]
    )
    response = ollama.chat(
        model=get_ollama_model(),
        messages=messages,
        options={"temperature": 0.0, "num_predict": 250},
        format=MasterIntentSchema.model_json_schema(),
    )
    raw = response["message"]["content"].strip()
    if not raw.endswith('}'): raw += '}'
    print(f"\U0001f50d [PASS-2] Raw ({intent}): {raw}")
    return MasterIntentSchema.model_validate_json(raw)


def parse_master_intent(user_msg: str, chat_history: list = None) -> MasterIntentSchema:
    """
    Bóc tách tên linh kiện + ý định bằng LLM 2-Stage Pipeline (Classification -> Extraction).
    Có kèm Guard Regex để bẻ lái lỗi và Retry on Mismatch.
    """
    history_context = ""
    if chat_history:
        history_context = "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\n"
        for msg in chat_history[-4:]:
            role = "Khách" if getattr(msg, "type", "") == "human" else "AI"
            content = msg.content
            if len(content) > 200 and role == "AI":
                content = content[:200] + "..."
            history_context += f"{role}: {content}\n"
        history_context += "\n"

    try:
        # 1. PASS 1
        intent_pass1 = _run_classification_pass(user_msg, history_context)
        
        # 2. Guard trước Pass 2: Regex phát hiện tương thích mà Pass 1 nhận nhầm
        compat_triggers = ['lắp với', 'đi với', 'tương thích', 'lắp được', 'chạy được', 'hợp không', 'đi cùng', 'vừa không', 'cắm được', 'gắn được', 'kết hợp', 'có ổn không', 'có sao không', 'phối với', 'ghép với', 'chạy chung']
        msg_l = user_msg.lower()
        has_compat_trigger = any(t in msg_l for t in compat_triggers)
        
        cpu_match = re.search(r'(amd ryzen\s*[3579]\s+\d{4,5}[a-z0-9]*|intel core i[3579][-\s]?\d{4,5}[a-z0-9]*|ryzen\s*[3579]\s+\d{4,5}[a-z0-9]*|i[3579][-\s]?\d{4,5}[a-z0-9]*|ryzen\s+[3579])', msg_l)
        gpu_match = re.search(r'((?:geforce\s+)?(?:rtx|gtx)\s*\d{3,4}(?:\s*ti|\s*super)?(?:\s*gaming)?(?:\s*\d{1,2}g)?|radeon\s+rx\s*\d{3,4}(?:\s*xt)?|rx\s*\d{3,4}(?:\s*xt)?)', msg_l)
        main_match = re.search(r'(asus\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|gigabyte\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|msi\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|asrock\s+[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|[bzhx]\d{2,3}m?(?:-[a-z0-9]+)?|mainboard\s+[a-z0-9-]+|main\s+[a-z0-9-]+)', msg_l)
        
        comp_count = sum(1 for x in [cpu_match, gpu_match, main_match] if x)
        
        if has_compat_trigger and comp_count >= 2 and intent_pass1 != "compatibility":
            print(f"\u26a0\ufe0f [GUARD] Pass 1 phân loại nhầm ({intent_pass1}). Ép thành 'compatibility'.")
            intent_pass1 = "compatibility"
            
        # 3. PASS 2
        parsed = _run_extraction_pass(user_msg, intent_pass1, history_context)
        parsed.intent = intent_pass1 # Khóa cứng intent từ Pass 1 (tránh Pass 2 tự ý đổi bậy)
        
        # 4. Guard sau Pass 2: Tách gộp + Retry Mismatch
        needs_retry = False
        fallback_intent = None
        
        # Tách gộp target_product (Ví dụ LLM Pass 2 lười gộp hết vào 1 cục)
        if parsed.target_product and parsed.target_product.lower() != "none":
            tp_lower = parsed.target_product.lower()
            tp_comp_count = sum(1 for match in [cpu_match, gpu_match, main_match] if match and match.group(1) in tp_lower)
            if tp_comp_count >= 2:
                print(f"[INTENT-GUARD] Tách entity từ target_product bị gộp: '{parsed.target_product}'")
                if cpu_match and cpu_match.group(1) in tp_lower and parsed.cpu == "none": parsed.cpu = cpu_match.group(1)
                if gpu_match and gpu_match.group(1) in tp_lower and parsed.gpu == "none": parsed.gpu = gpu_match.group(1)
                if main_match and main_match.group(1) in tp_lower and parsed.mainboard == "none": parsed.mainboard = main_match.group(1)
                parsed.target_product = "none"

        # Regex Rescue (cứu dữ liệu nếu LLM bỏ quên)
        if parsed.intent == "compatibility" and comp_count >= 2:
            if parsed.cpu == "none" and cpu_match: parsed.cpu = cpu_match.group(1)
            if parsed.gpu == "none" and gpu_match: parsed.gpu = gpu_match.group(1)
            if parsed.mainboard == "none" and main_match: parsed.mainboard = main_match.group(1)

        # Retry logic
        if parsed.intent == "compatibility":
            named_items = [parsed.cpu, parsed.mainboard, parsed.gpu]
            valid_named = [i for i in named_items if i and i.strip().lower() != "none"]
            has_target = parsed.target_product and parsed.target_product.strip().lower() != "none"
            total_items = len(valid_named) + (1 if has_target else 0)
            if total_items <= 1:
                needs_retry = True
                fallback_intent = "suggestion"
                
        elif parsed.intent == "price_calculation":
            named_items = [parsed.cpu, parsed.mainboard, parsed.gpu]
            valid_named = [i for i in named_items if i and i.strip().lower() != "none"]
            has_target = parsed.target_product and parsed.target_product.strip().lower() != "none"
            total_items = len(valid_named) + (1 if has_target and not valid_named else 0)
            if total_items <= 1:
                needs_retry = True
                fallback_intent = "price_check"

        if needs_retry and fallback_intent:
            print(f"\u26a0\ufe0f [RETRY] Guard detected mismatch ({parsed.intent} \u2192 {fallback_intent}). Retrying Pass 2...")
            parsed = _run_extraction_pass(user_msg, fallback_intent, history_context)
            parsed.intent = fallback_intent # Khóa cứng intent sau khi retry
            # Apply guard post-retry for safety
            if fallback_intent == "suggestion" and parsed.target_product != "none":
                tp = parsed.target_product.lower()
                if any(k in tp for k in ["ryzen", "i3", "i5", "i7", "i9", "core", "cpu", "chip"]): parsed.cpu = parsed.target_product
                elif any(k in tp for k in ["rtx", "gtx", "rx ", "radeon", "geforce"]): parsed.gpu = parsed.target_product
                else: parsed.cpu = parsed.target_product
                parsed.target_product = "none"

        return parsed
        
    except Exception as e:
        print(f"\u274c [INTENT-LLM] Lỗi parse intent, fallback 'none': {e}")
        return MasterIntentSchema(
            reasoning="Fallback do lỗi kết nối LLM",
            intent="none", target_product="none", spec_detail="none",
            cpu="none", mainboard="none", gpu="none", budget_amount=0, category="none"
        )