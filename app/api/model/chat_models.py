from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator


MessageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
SessionId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]


class ChatRequest(BaseModel):
    user_message: MessageText = Field(description="User message")
    session_id: SessionId = Field("default", description="Chat session id")


class EvalChatRequest(ChatRequest):
    pass


class ChatResponse(BaseModel):
    chatbot_reply: str = Field(description="Final chatbot reply")


class EvalChatResponse(ChatResponse):
    contexts: list[str] = Field(default_factory=list, description="Raw evaluation contexts")


class ErrorResponse(BaseModel):
    error: str = Field(description="Error type")
    message: str = Field(description="Human-readable error message")
    code: str = Field(description="Stable application error code")


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str = "local"

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("input must not be empty")
            return value

        values = [item.strip() for item in value]
        if not values or any(not item for item in values):
            raise ValueError("input must contain non-empty strings")
        return values


class EmbeddingData(BaseModel):
    object: Literal["embedding"] = "embedding"
    index: int
    embedding: list[float]


class EmbeddingUsage(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[EmbeddingData]
    model: str
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)


class DeleteSessionResponse(BaseModel):
    status: Literal["ok"] = "ok"
    message: str
