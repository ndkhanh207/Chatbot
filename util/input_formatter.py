from pydantic import BaseModel, Field
from typing import Literal

# Định nghĩa cấu trúc dữ liệu mong muốn
class PCIntentSchema(BaseModel):
    intent: Literal["compatibility", "suggestion", "general"] = Field(
        description="compatibility nếu hỏi tương thích, suggestion nếu nhờ tư vấn, general nếu chat linh tinh"
    )
    cpu: str = Field(description="Tên CPU có trong câu, nếu không có ghi 'none'")
    mainboard: str = Field(description="Tên Mainboard có trong câu, nếu không có ghi 'none'")
    gpu: str = Field(description="Tên GPU/Card đồ họa có trong câu, nếu không có ghi 'none'")