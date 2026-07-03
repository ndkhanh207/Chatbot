from pydantic import BaseModel, Field, field_validator
import re

class ChatRequest(BaseModel):
    user_message: str = Field(..., max_length=1000, description="Tin nhắn gửi lên từ người dùng")
    session_id: str = Field("default", max_length=100, min_length=1, pattern="^[a-zA-Z0-9_-]+$", description="ID của phiên hội thoại")

    @field_validator('user_message')
    @classmethod
    def check_prompt_injection(cls, v: str) -> str:
        # Bộ lọc từ khóa chặn Prompt Injection cơ bản
        forbidden_patterns = [
            r"ignore\s+all\s+previous",
            r"system\s+prompt",
            r"bỏ\s+qua\s+(các\s+)?lệnh",
            r"quên\s+hết\s+(các\s+)?lệnh",
        ]
        # Âm thầm xóa bỏ các từ khóa độc hại thay vì báo lỗi để không đánh động hacker
        for pattern in forbidden_patterns:
            v = re.sub(pattern, "", v, flags=re.IGNORECASE)
            
        return v.strip()

class EvalChatRequest(ChatRequest):
    magic_key: str = Field(..., description="Khóa bí mật dùng cho Rag evaluation")

class ChatResponse(BaseModel):
    chatbot_reply: str = Field(..., description="Nội dung phản hồi chính thức từ AI Chatbot")
    contexts: list[str] | None = Field(None, description="Danh sách context thô (chỉ trả về khi có magic_key hợp lệ)")

class ErrorResponse(BaseModel):
    error: str = Field(..., description="Phân loại lỗi (VD: Validation Error, Timeout Error, Internal Server Error)")
    message: str = Field(..., description="Thông báo mô tả chi tiết nguyên nhân lỗi")
    code: str = Field(..., description="Mã lỗi định danh hệ thống (VD: EMPTY_MESSAGE, INVALID_SESSION_ID)")
