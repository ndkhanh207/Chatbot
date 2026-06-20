import ollama
from pydantic import BaseModel
from typing import Literal

from util.model_utils import get_ollama_model

class PCIntentSchema(BaseModel):
    intent: Literal["compatibility", "suggestion", "price_calculation", "none"] = "none"
    cpu: str = "none"
    mainboard: str = "none"
    gpu: str = "none"
    looking_for: Literal["cpu", "mainboard", "gpu", "none"] = "none"


_INTENT_SYSTEM_PROMPT = (
    "Bạn là AI chuyên bóc tách thông tin phần cứng PC từ câu hỏi của khách. "
    "Tìm tên CPU, Mainboard, GPU ĐƯỢC CHỈ ĐỊNH CỤ THỂ (ví dụ: 'i5 12400f', 'h610m', 'rtx 3060') "
    "để xác định ý định:\n"
    "- 'compatibility': khách hỏi 2 linh kiện CỤ THỂ có lắp/chạy được với nhau không.\n"
    "- 'suggestion': khách đã có ĐÚNG 1 linh kiện cụ thể, muốn tìm linh kiện "
    "còn lại phù hợp với nó.\n"
    "- 'price_calculation': khách liệt kê danh sách linh kiện và muốn tính TỔNG GIÁ/TỔNG TIỀN của chúng.\n"
    "- 'none': câu hỏi khác (mua theo giá, hỏi thông số, không nhắc linh kiện cụ thể).\n"
    "LƯU Ý QUAN TRỌNG: KHÔNG trích xuất các từ chung chung (như 'main', 'mainboard', 'cpu', 'gpu', 'card', 'bo mạch chủ') "
    "vào trường tên linh kiện. Chỉ trích xuất khi khách nhắc đến TÊN/MÃ cụ thể. "
    "Nếu không có tên linh kiện cụ thể cho 1 mục, điền 'none' cho mục đó.\n"
    "Trường 'looking_for': Loại linh kiện mà khách ĐANG TÌM KIẾM (ví dụ khách hỏi 'tìm main' -> 'mainboard', 'chọn card' -> 'gpu'). Nếu không rõ, trả về 'none'."
)

_INTENT_FEWSHOT = [
    {"role": "user", "content": "i5 12400f phối với h610m ổn ko admin"},
    {"role": "assistant", "content": '{"intent": "compatibility", "cpu": "i5 12400f", "mainboard": "h610m", "gpu": "none", "looking_for": "none"}'},
    {"role": "user", "content": "tôi có cpu ryzen 9 9950x3d rồi, tìm gpu phù hợp"},
    {"role": "assistant", "content": '{"intent": "suggestion", "cpu": "ryzen 9 9950x3d", "mainboard": "none", "gpu": "none", "looking_for": "gpu"}'},
    {"role": "user", "content": "tìm cho tôi main phù hợp với cpu i9 14900K"},
    {"role": "assistant", "content": '{"intent": "suggestion", "cpu": "i9 14900k", "mainboard": "none", "gpu": "none", "looking_for": "mainboard"}'},
    {"role": "user", "content": "tôi lấy main asus z790 và i9 14900k tổng bao nhiêu"},
    {"role": "assistant", "content": '{"intent": "price_calculation", "cpu": "i9 14900k", "mainboard": "asus z790", "gpu": "none", "looking_for": "none"}'},
    # Đổi khác ví dụ gốc: đây là câu hỏi mua theo giá, KHÔNG phải "đã có
    # 1 linh kiện, tìm linh kiện còn lại" — nên gán "none" để rơi xuống
    # nhánh xử lý giá thông thường, không lẫn vào compat.
    {"role": "user", "content": "tư vấn em con card tầm 4 triệu"},
    {"role": "assistant", "content": '{"intent": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "looking_for": "gpu"}'},
    {"role": "user", "content": "tìm cho tôi gpu nvidia phù hợp giá 20 triệu"},
    {"role": "assistant", "content": '{"intent": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "looking_for": "gpu"}'},
]


def parse_compat_intent(user_msg: str) -> PCIntentSchema:
    """
    Bóc tách tên linh kiện + ý định bằng LLM (Ollama structured output).
    LƯU Ý ĐÁNH ĐỔI: thêm 1 lượt gọi LLM mỗi khi is_compatibility_query()
    trigger (ngoài reformulate + chain trả lời chính) → tăng latency cho
    câu hỏi compat. Nếu LLM lỗi/timeout, trả về intent='none' (an toàn —
    rơi xuống product_context bình thường, không crash).
    """
    messages = (
        [{"role": "system", "content": _INTENT_SYSTEM_PROMPT}]
        + _INTENT_FEWSHOT
        + [{"role": "user", "content": user_msg}]
    )
    try:
        response = ollama.chat(
            model=get_ollama_model(),
            messages=messages,
            options={"temperature": 0.0},
            format=PCIntentSchema.model_json_schema(),
        )
        parsed = PCIntentSchema.model_validate_json(response["message"]["content"])
        
        # Guard: Chống LLM 1.5B bị "ngáo" (phân loại nhầm 'compatibility' khi chỉ có 1 món)
        if parsed.intent == "compatibility":
            items = [parsed.cpu, parsed.mainboard, parsed.gpu]
            valid_items = [i for i in items if i and i.strip().lower() != "none"]
            if len(valid_items) == 1:
                print(f"[INTENT-GUARD] LLM ngáo đá, phân loại 'compatibility' nhưng chỉ có 1 món ({valid_items[0]}). Ép kiểu về 'suggestion'.")
                parsed.intent = "suggestion"
                if not parsed.looking_for or parsed.looking_for.lower() == "none":
                    parsed.looking_for = "unknown" # Để hệ thống biết khách đang tìm món khác ghép vào
                
        return parsed
    except Exception as e:
        print(f"[INTENT-LLM] Lỗi parse intent, fallback 'none': {e}")
        return PCIntentSchema()
