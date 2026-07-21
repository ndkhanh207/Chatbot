import ollama
from app.utils.model_utils import get_ollama_model
from app.llm.gateway import safe_llm_call
from app.llm.result import LlmResult
from app.rag.models import GroundedAnswerRequest, GroundedAnswer

SYSTEM_PROMPT = """\
You are a PC shop assistant.

Answer the user's question using only the supplied evidence.

Rules:
- Never invent product names, prices, specifications or IDs.
- Never change computed totals or compatibility statuses.
- If evidence is insufficient, say which information is unavailable.
- Do not mention internal retrieval or evidence structures.
- Answer naturally in the user's language.
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
