from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    user_message: str = Field(..., description="Tin nhắn gửi lên từ người dùng")
    session_id: str = Field("default", description="ID của phiên hội thoại")

class ChatResponse(BaseModel):
    chatbot_reply: str = Field(..., description="Nội dung phản hồi chính thức từ AI Chatbot")

class ErrorResponse(BaseModel):
    error: str = Field(..., description="Phân loại lỗi (VD: Validation Error, Timeout Error, Internal Server Error)")
    message: str = Field(..., description="Thông báo mô tả chi tiết nguyên nhân lỗi")
    code: str = Field(..., description="Mã lỗi định danh hệ thống (VD: EMPTY_MESSAGE, INVALID_SESSION_ID)")
