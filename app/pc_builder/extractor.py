import json
import re
from typing import Any

from app.pc_builder.models import PcBuildCommand, PcBuildAction
from app.pc_builder.models import PcBuildContext
from app.routing.models import RouteDecision
from app.llm.gateway import safe_llm_call, LlmResult
from app.utils.model_utils import get_ollama_model
import ollama

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

ROLE_MAP = {
    "human": "user",
    "user": "user",
    "ai": "assistant",
    "assistant": "assistant",
    "system": "system",
}

def _extract_message(
    message: Any,
) -> tuple[str, str]:
    if isinstance(message, dict):
        raw_role = str(
            message.get("role", "unknown")
        )
        content = str(
            message.get("content", "")
        )
    else:
        raw_role = str(
            getattr(message, "type", "unknown")
        )
        content = str(
            getattr(message, "content", "")
        )

    role = ROLE_MAP.get(
        raw_role.casefold(),
        "unknown",
    )
    return role, content.strip()

def format_chat_history(
    messages: list,
    limit: int,
) -> str:
    """
    Chuyển lịch sử chat thành văn bản ngắn cho bước Interpretation.
    """
    if limit <= 0 or not messages:
        return ""

    formatted: list[str] = []

    for message in messages[-limit:]:
        role, content = _extract_message(message)

        if not content:
            continue

        formatted.append(
            f"{role}: {content}"
        )

    return "\n".join(formatted)

INTERPRET_SYSTEM_PROMPT = """Bạn là AI chuyên trích xuất lệnh cho chức năng Build PC.
Bạn nhận được ngữ cảnh hiện tại của bộ PC, lịch sử hội thoại, quyết định định tuyến và câu nói mới nhất của khách hàng.
Hãy trích xuất thông tin sang JSON chính xác nhất cho lớp PcBuildCommand.

YÊU CẦU QUAN TRỌNG NHẤT:
- action: Hành động người dùng muốn thực hiện:
    + create: Khi người dùng muốn tư vấn một bộ máy TỪ ĐẦU (kể cả khi đã có ngân sách, yêu cầu, hoặc chỉ là câu hỏi chung chung như "tư vấn pc").
    + update: Khi người dùng muốn thêm/bớt/đổi linh kiện, đổi nhu cầu, ngân sách HOẶC trả lời câu hỏi làm rõ từ bot.
    + alternative: Khi người dùng muốn ĐỔI SANG bộ khác (không muốn lấy bộ hiện tại). VD: "có bộ nào rẻ hơn không", "đổi bộ khác".
    + question_current_build: Khi người dùng hỏi thêm thông tin về bộ máy (VD: "bộ này chơi mượt không", "RAM hãng gì").
- budget: TÌM BẰNG ĐƯỢC số tiền khách yêu cầu (triệu, củ, k) và dịch ra số nguyên VND. KHÔNG ĐƯỢC TỰ Ý NHÂN CHIA, chỉ trích xuất đúng con số khách viết (kể cả khi mua nhiều bộ). Nếu khách nói "âm", "trừ" (VD: âm 30 triệu), BẮT BUỘC trả về số âm (VD: -30000000).
- budget_scope: "total" (nếu budget là tổng cho nhiều máy), "per_unit" (mỗi máy), "unknown" (không rõ).
- purpose: Trích xuất ĐÚNG NGUYÊN VĂN mục đích sử dụng khách viết. Không được tự ý tóm tắt. Nếu khách chỉ nói ngân sách hoặc linh kiện mà không đề cập mục đích, đặt purpose=null.
- purpose_status: "ready" nếu ĐỦ CỤ THỂ (có tên phần mềm, game cụ thể như LOL, Dota, Photoshop, Excel, v.v.); "clarify" nếu MƠ HỒ.
LƯU Ý ĐẶC BIỆT (QUAN TRỌNG): Những từ khóa như "chơi game", "làm việc", "văn phòng", "học tập", "cơ bản", "phổ thông", "nhẹ" mà KHÔNG KÈM THEO tên phần mềm/game cụ thể thì BẮT BUỘC purpose_status="clarify". Nếu bạn trả về "ready" cho "làm văn phòng", đó là LỖI NGHIÊM TRỌNG.

### VÍ DỤ:
User: "build pc 30 triệu chơi game"
Context: budget=null, purpose=null
=> action="create", budget=30000000, purpose="chơi game", purpose_status="clarify"

User: "build pc 30 triệu để làm việc"
Context: budget=null, purpose=null
=> action="create", budget=30000000, purpose="để làm việc", purpose_status="clarify"

User: "cho tôi con i9"
Context: budget=null, purpose="chơi game", purpose_status="clarify"
=> action="update", required_components={"CPU": "Intel Core i9"}, purpose=null, purpose_status=null

User: "chơi game valorant"
Context: budget=30M, purpose="chơi game", purpose_status="clarify"
=> action="update", budget=null, purpose="chơi game valorant", purpose_status="ready"

User: "cho tôi hỏi máy này có chơi được valorant ko"
Context: budget=30M, purpose="chơi game valorant nhẹ", purpose_status="ready"
=> action="question_current_build" (vì đang hỏi về bộ hiện tại)
- keep_components: Các linh kiện khách BẢO GIỮ LẠI (VD: giữ nguyên cpu -> ["cpu"]).
- required_components: Các linh kiện khách YÊU CẦU MỚI hoặc ĐỔI SANG. BẮT BUỘC trích xuất nếu khách nhắc đến tên linh kiện (VD: đổi sang rtx 4080 -> {"gpu": "rtx 4080"}). KHÔNG ĐƯỢC để trống nếu khách có nhắc.

BẮT BUỘC trả về JSON theo đúng schema của PcBuildCommand.
"""

def _get_async_client():
    return ollama.AsyncClient()

async def _extract_command(
    user_message: str,
    recent_history: list[str],
    current_context: PcBuildContext,
    route_decision: RouteDecision,
) -> PcBuildCommand:
    messages = [
        {
            "role": "system",
            "content": INTERPRET_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                "Trạng thái bộ PC hiện tại:\n"
                f"{current_context.model_dump_json(indent=2)}\n\n"
                "Quyết định định tuyến (cho biết hướng xử lý chung):\n"
                f"{route_decision.model_dump_json(indent=2)}\n\n"
                "Lịch sử gần đây:\n"
                f"{chr(10).join(msg.content if hasattr(msg, 'content') else str(msg) for msg in recent_history)}\n\n"
                "Câu nói mới nhất:\n"
                f"{user_message}"
            ),
        },
    ]
    
    response = await _get_async_client().chat(
        model=get_ollama_model(),
        messages=messages,
        options={"temperature": 0.0, "num_predict": 512},
        format=PcBuildCommand.model_json_schema(),
    )
    
    command = PcBuildCommand.model_validate_json(response["message"]["content"])
    
    # Fallback and adjustments
    fallback_budget = extract_budget_fallback(user_message)
    if fallback_budget is not None and fallback_budget < 0:
        command.budget = fallback_budget
    elif command.budget is None and fallback_budget is not None:
        command.budget = fallback_budget
        
    if command.budget is not None and command.budget > 0 and fallback_budget is not None:
        if command.quantity and command.quantity > 1 and command.budget > fallback_budget:
            command.budget = fallback_budget
            command.budget_scope = "total"
            
    if not command.required_components:
        fallback_comps = extract_components_fallback(user_message)
        if fallback_comps:
            command.required_components = fallback_comps  # type: ignore
            
    return command

async def extract_pc_build_command(
    *,
    user_message: str,
    recent_history: list[str],
    current_context: PcBuildContext,
    route_decision: RouteDecision,
) -> LlmResult[PcBuildCommand]:
    return await safe_llm_call(
        lambda: _extract_command(
            user_message=user_message,
            recent_history=recent_history,
            current_context=current_context,
            route_decision=route_decision,
        ),
        timeout_seconds=12,
        max_attempts=2,
        operation_name="extract_pc_build_command",
    )
