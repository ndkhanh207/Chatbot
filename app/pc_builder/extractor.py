import json
import re
import asyncio
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
import ollama
from app.utils.model_utils import get_ollama_model

class InterpretationError(Exception):
    pass



BUILD_KEYWORDS = [
    "build pc", "build máy", "build", "ráp pc", "lắp pc", "ráp máy", "lắp máy", "cấu hình", "dàn máy", "mua máy",
    "bộ pc", "máy tính bàn", "desktop", "tư vấn pc", "tư vấn máy", "gợi ý pc", "máy tính", "bộ máy", "thùng máy"
]

def detect_build_pc_intent(msg: str) -> bool:
    msg_l = msg.lower()
    return any(kw in msg_l for kw in BUILD_KEYWORDS)

def extract_budget_fallback(msg: str) -> int | None:
    match = re.search(r'(-|âm\s+)?(\d+)\s*(triệu|củ|tr|trieu|cu)\b', msg, flags=re.IGNORECASE)
    if match:
        sign = -1 if match.group(1) else 1
        return sign * int(match.group(2)) * 1000000
    return None

def extract_explicit_build_id(msg: str) -> str | None:
    match = re.search(r'\bBUILD[-_]\d+\b', msg, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return None

def extract_components_fallback(msg: str) -> dict[str, str]:
    comps = {}
    cpu_match = re.search(r'\b(i[3579]\s*\d+[a-z]*|ryzen\s*\d\s*\d+[a-z]*|xeon|pentium|celeron|intel|amd)\b', msg, flags=re.IGNORECASE)
    if cpu_match:
        comps["cpu"] = cpu_match.group(1).lower()
    gpu_match = re.search(r'\b((?:rtx|gtx|rx|radeon|geforce|arc)\s*\d+[a-z]*|nvidia)\b', msg, flags=re.IGNORECASE)
    if gpu_match:
        comps["gpu"] = gpu_match.group(1).lower()
    return comps

def answers_pending_question(
    message: str,
    pending_question: str | None,
) -> bool:
    if not pending_question:
        return False

    text = " ".join(
        message.strip().casefold().split()
    )

    if pending_question == "budget":
        return any(char.isdigit() for char in text)


    return False

ComponentCategory = Literal["cpu", "gpu", "mainboard"]
BudgetScope = Literal["total", "per_unit", "unknown"]

class Interpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: Literal["pc_builder", "current_build_qa", "pass"]
    action: Literal["continue", "reset", "alternative"] = "continue"

    budget: int | None = Field(default=None)
    budget_scope: BudgetScope = "unknown"
    quantity: int | None = Field(default=None, ge=1, le=100)
    purpose: str | None = Field(default=None, max_length=300)

    required_components: dict[ComponentCategory, str] = Field(default_factory=dict)
    preferred_components: dict[ComponentCategory, list[str]] = Field(default_factory=dict)
    excluded_brands: list[str] = Field(default_factory=list)

    keep_components: list[ComponentCategory] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def clean_categories(cls, data: dict):
        valid_comps = {"cpu", "gpu", "mainboard"}
        for key in ["required_components", "preferred_components"]:
            if key in data and isinstance(data[key], dict):
                data[key] = {k: v for k, v in data[key].items() if k in valid_comps}
        if "keep_components" in data and isinstance(data["keep_components"], list):
            data["keep_components"] = [k for k in data["keep_components"] if k in valid_comps]
        return data

INTERPRET_SYSTEM_PROMPT = """Bạn là AI đọc hiểu yêu cầu ráp PC.
Bạn nhận được lịch sử hội thoại, cấu hình hiện tại và câu nói mới nhất của khách hàng.
Hãy trích xuất thông tin sang JSON chính xác nhất.

YÊU CẦU QUAN TRỌNG NHẤT:
- budget: TÌM BẰNG ĐƯỢC số tiền khách yêu cầu (triệu, củ, k) và dịch ra số nguyên VND. KHÔNG ĐƯỢC TỰ Ý NHÂN CHIA, chỉ trích xuất đúng con số khách viết (kể cả khi mua nhiều bộ). Nếu khách nói "âm", "trừ" (VD: âm 30 triệu), BẮT BUỘC trả về số âm (VD: -30000000).
- budget_scope: "total" (nếu budget là tổng cho nhiều máy), "per_unit" (mỗi máy), "unknown" (không rõ).
- purpose: Trích xuất ĐÚNG NGUYÊN VĂN mục đích sử dụng khách viết (VD: "văn phòng", "esport", "render", "chơi game"). Không được tự ý tóm tắt.
- keep_components: Các linh kiện khách BẢO GIỮ LẠI (VD: giữ nguyên cpu -> ["cpu"]).
- required_components: Các linh kiện khách YÊU CẦU MỚI hoặc ĐỔI SANG. BẮT BUỘC trích xuất nếu khách nhắc đến tên linh kiện (VD: đổi sang rtx 4080 -> {"gpu": "rtx 4080"}). KHÔNG ĐƯỢC để trống nếu khách có nhắc.
- route: Chọn "pc_builder" nếu đang ráp máy, "current_build_qa" nếu hỏi về bộ hiện tại, "pass" nếu hỏi vớ vẩn ngoài lề.
- action: "continue", "reset", "alternative". BẮT BUỘC trả về "continue" nếu khách yêu cầu đổi/giữ linh kiện.
- BẮT BUỘC trả về JSON theo ĐÚNG định dạng sau:
{
  "route": "pc_builder",
  "action": "continue",
  "budget": 35000000,
  "budget_scope": "per_unit",
  "purpose": "chơi game",
  "quantity": 1,
  "keep_components": [],
  "required_components": {"cpu": "ryzen 9 7950x"},
  "preferred_components": {},
  "excluded_brands": []
}
"""

def _get_async_client():
    return ollama.AsyncClient()

async def interpret_build_turn(
    user_message: str,
    chat_history: str,
    trusted_snapshot: dict,
    forced_route: str | None = None,
) -> Interpretation:
    system_prompt = INTERPRET_SYSTEM_PROMPT
    if forced_route:
        system_prompt += f"\nCHÚ Ý: Lượt này BẮT BUỘC đặt route='{forced_route}' (không được trả route='pass'). Tuy nhiên bạn vẫn phải trích xuất các thông tin khác từ câu mới nhất."

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": (
                "Trạng thái ứng dụng hiện tại:\n"
                f"{json.dumps(trusted_snapshot, ensure_ascii=False)}\n\n"
                "Lịch sử gần đây:\n"
                f"{chat_history}\n\n"
                "Câu nói mới nhất:\n"
                f"{user_message}"
            ),
        },
    ]
    
    response = await _get_async_client().chat(
        model=get_ollama_model(),
        messages=messages,
        options={"temperature": 0.0, "num_predict": 512},
        format=Interpretation.model_json_schema(),
    )
    raw = response["message"]["content"].strip()
    print("====== EXTRACTOR RAW ======")
    print(raw)
    print("===========================")
    interpretation = Interpretation.model_validate_json(response["message"]["content"])
    fallback_budget = extract_budget_fallback(user_message)
    if fallback_budget is not None and fallback_budget < 0:
        interpretation.budget = fallback_budget
    elif interpretation.budget is None and fallback_budget is not None:
        interpretation.budget = fallback_budget
        
    if interpretation.budget is not None and interpretation.budget > 0 and fallback_budget is not None:
        # Prevent LLM from multiplying budget by quantity
        if interpretation.quantity and interpretation.quantity > 1 and interpretation.budget > fallback_budget:
            print(f"DEBUG: Overriding LLM budget {interpretation.budget} with fallback {fallback_budget}")
            interpretation.budget = fallback_budget
            interpretation.budget_scope = "total"
            
    print(f"DEBUG: Final interpretation={interpretation.model_dump()}")
    
    if not interpretation.required_components:
        fallback_comps = extract_components_fallback(user_message)
        if fallback_comps:
            interpretation.required_components = fallback_comps  # type: ignore
            
    return interpretation

from app.llm.gateway import safe_llm_call
from app.llm.result import LlmResult

async def interpret_build_turn_safe(
    *,
    user_message: str,
    chat_history: str,
    trusted_snapshot: dict,
    forced_route: str | None = None,
) -> LlmResult[Interpretation]:
    return await safe_llm_call(
        lambda: interpret_build_turn(
            user_message=user_message,
            chat_history=chat_history,
            trusted_snapshot=trusted_snapshot,
            forced_route=forced_route,
        ),
        timeout_seconds=12,
        max_attempts=2,
        operation_name="pc_builder_interpretation",
    )
