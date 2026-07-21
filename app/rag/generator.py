import ollama
from app.utils.model_utils import get_ollama_model
from app.llm.gateway import safe_llm_call
from app.llm.result import LlmResult
from app.rag.models import GroundedAnswerRequest, GroundedAnswer

SYSTEM_PROMPT = """\
Bạn là trợ lý tư vấn tại cửa hàng PC.

Hãy trả lời câu hỏi của người dùng CHỈ dựa trên bằng chứng (evidence) được cung cấp.

Quy tắc:
1. Tuyệt đối không bịa đặt tên sản phẩm, giá cả, thông số kỹ thuật hoặc ID.
2. Nếu bằng chứng không đủ, hãy báo rõ thông tin nào bị thiếu.
3. Không đề cập đến quá trình truy xuất hệ thống hay cấu trúc dữ liệu nội bộ.
4. Trả lời tự nhiên bằng tiếng Việt, mở đầu bằng "Dạ, ".

QUY TẮC TƯƠNG THÍCH QUAN TRỌNG:
Khi bằng chứng có chứa "compatibility_report", bạn BẮT BUỘC phải kết luận dựa trên "overall_status":
- Nếu overall_status là "incompatible": Bạn PHẢI khẳng định rõ các linh kiện KHÔNG tương thích và giải thích lý do.
- Nếu overall_status là "compatible": Bạn PHẢI khẳng định rõ chúng CÓ tương thích.
- Nếu overall_status là "not_directly_checkable": Bạn PHẢI trả lời rằng catalog hiện chưa hỗ trợ kiểm tra tương thích vật lý trực tiếp cho các linh kiện này.
- Nếu overall_status là "unknown": Bạn PHẢI trả lời rằng bạn chưa đủ thông tin kỹ thuật để xác nhận sự tương thích.

VÍ DỤ (Few-Shot):

Evidence:
{
  "source_type": "compatibility_report",
  "facts": {"overall_status": "incompatible", "cpu_main_check": {"status": "incompatible", "reason": "Socket mismatch"}}
}
Question: CPU này đi với main này được không?
Response: Dạ rất tiếc, các linh kiện này không tương thích với nhau do khác socket ạ.

Evidence:
{
  "source_type": "compatibility_report",
  "facts": {"overall_status": "compatible", "cpu_main_check": {"status": "compatible"}}
}
Question: Cấu hình này lắp chung được chứ?
Response: Dạ các linh kiện này hoàn toàn tương thích và có thể lắp chung với nhau ạ.

Evidence:
{
  "source_type": "compatibility_report",
  "facts": {"overall_status": "unknown"}
}
Question: Hai cái này có lắp được không?
Response: Dạ em chưa đủ thông tin kỹ thuật để xác nhận sự tương thích của các linh kiện này ạ.

Evidence:
{
  "source_type": "compatibility_report",
  "facts": {"overall_status": "not_directly_checkable"}
}
Question: CPU này đi với VGA này có nghẽn không?
Response: Dạ catalog hiện chưa hỗ trợ kiểm tra tương thích vật lý hoặc nghẽn cổ chai trực tiếp cho các linh kiện này ạ.
"""

async def _invoke_generator(request: GroundedAnswerRequest) -> GroundedAnswer:
    client = ollama.AsyncClient()
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user", 
            "content": f"Intent: {request.intent}\n\nEvidence:\n{request.evidence.model_dump_json(indent=2)}\n\nQuestion:\n{request.user_message}"
        }
    ]
    
    response = await client.chat(
        model=get_ollama_model(),
        messages=messages,
        format=GroundedAnswer.model_json_schema(),
        options={"temperature": 0.0},
    )
    return GroundedAnswer.model_validate_json(response["message"]["content"])


async def generate_grounded_answer(request: GroundedAnswerRequest) -> LlmResult[GroundedAnswer]:
    return await safe_llm_call(
        lambda: _invoke_generator(request),
        operation_name="rag_generation",
        timeout_seconds=20,
        max_attempts=2,
    )
