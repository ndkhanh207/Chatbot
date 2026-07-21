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
5. GIỮ NGUYÊN chuỗi ký tự giá tiền y như trong bằng chứng. TUYỆT ĐỐI KHÔNG bỏ sót số 0 nào ở cuối giá tiền (ví dụ: 19.919.760 phải giữ nguyên 19.919.760, không được viết thành 1.991.976). KHÔNG THÊM BỚT BẤT KỲ SỐ NÀO.

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
Response:
{
  "reply": "Dạ rất tiếc, các linh kiện này không tương thích với nhau do khác socket ạ."
}

Evidence:
{
  "source_type": "compatibility_report",
  "facts": {"overall_status": "compatible", "cpu_main_check": {"status": "compatible"}}
}
Question: Cấu hình này lắp chung được chứ?
Response:
{
  "reply": "Dạ các linh kiện này hoàn toàn tương thích và có thể lắp chung với nhau ạ."
}

Evidence:
{
  "source_type": "product",
  "facts": {"name": "MSI GeForce RTX 5070 Ti", "price": "19.919.760"}
}
Question: rtx 5070 ti giá bao nhiêu?
Response:
{
  "reply": "Dạ, MSI GeForce RTX 5070 Ti hiện có giá là 19.919.760 VNĐ ạ."
}

Evidence:
{
  "source_type": "compatibility_report",
  "facts": {"overall_status": "unknown"}
}
Question: Hai cái này có lắp được không?
Response:
{
  "reply": "Dạ em chưa đủ thông tin kỹ thuật để xác nhận sự tương thích của các linh kiện này ạ."
}

Evidence:
{
  "source_type": "compatibility_report",
  "facts": {"overall_status": "not_directly_checkable"}
}
Question: CPU này đi với VGA này có nghẽn không?
Response:
{
  "reply": "Dạ catalog hiện chưa hỗ trợ kiểm tra tương thích vật lý hoặc nghẽn cổ chai trực tiếp cho các linh kiện này ạ."
}
"""

async def _invoke_generator(request: GroundedAnswerRequest) -> GroundedAnswer:
    client = ollama.AsyncClient()
    
    prompt = f"Intent: {request.intent}\n\nEvidence:\n{request.evidence.model_dump_json(indent=2)}\n\nQuestion:\n{request.user_message}"
    print(f"\n[DEBUG] LLM Prompt:\n{prompt}\n")
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
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
