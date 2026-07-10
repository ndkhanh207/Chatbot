import re

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    user_message: str = Field(..., max_length=1000, description="User message")
    session_id: str = Field("default", max_length=100, min_length=1, description="Chat session id")

    @field_validator("user_message")
    @classmethod
    def check_prompt_injection(cls, v: str) -> str:
        forbidden_patterns = [
            r"ignore\s+all\s+previous",
            r"system\s+prompt",
            r"bỏ\s+qua\s+(các\s+)?lệnh",
            r"quên\s+hết\s+(các\s+)?lệnh",
        ]
        for pattern in forbidden_patterns:
            v = re.sub(pattern, "", v, flags=re.IGNORECASE)

        return v.strip()


class EvalChatRequest(ChatRequest):
    magic_key: str = Field(..., description="RAG evaluation secret key")


class ChatResponse(BaseModel):
    chatbot_reply: str = Field(..., description="Final chatbot reply")
    contexts: list[str] | None = Field(None, description="Raw contexts for evaluation")


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    code: str = Field(..., description="Stable application error code")
