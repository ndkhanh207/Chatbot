"""Prompts for handler-scoped entity extraction.

Routing is already complete before these prompts are used. The extractor must
never select, repair, or replace a handler.
"""

_SYSTEM_EXTRACT = """
Bạn có nhiệm vụ trích xuất các thực thể (entities) có cấu trúc từ tin nhắn tiếng Việt của người dùng.
Handler đã được chọn sẵn và cung cấp trong thẻ <system_hint>. Hãy coi nó là cố định:
sao chép chính xác nó vào trường `intent` và tuyệt đối không phân loại hay thay đổi luồng của tin nhắn.

Chỉ trả về các trường được yêu cầu bởi JSON schema. Chỉ trích xuất những thông tin có thật
được nhắc đến trong <user_input>. Không sao chép tên sản phẩm từ các ví dụ và không được
tự bịa ra các giá trị bị thiếu. Sử dụng `null` nếu không có thông tin (chữ) và `0` nếu không có ngân sách (số).
Chuyển đổi các mệnh giá tiền tệ tiếng Việt thành số nguyên VND (ví dụ: 8 triệu là 8000000, 500k là 500000).

Các trường dữ liệu:
- target_product: tên cụ thể của sản phẩm, thương hiệu, hoặc từ khóa tìm kiếm
- spec_detail: thông số kỹ thuật hoặc nhu cầu hiệu năng cụ thể được yêu cầu, ví dụ như
  vram, xung nhịp, render, hoặc "chơi PUBG mượt"
- cpu, gpu, mainboard: các linh kiện được chỉ đích danh
- budget_amount: ngân sách yêu cầu tính bằng VND
- category: danh mục sản phẩm yêu cầu như cpu, gpu, mainboard, ram, ssd
""".strip()


def _example(user: str, assistant: str) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]


_FEWSHOT_BY_INTENT = {
    "compatibility": (
        _example(
            "<system_hint>Handler = compatibility</system_hint>\n<user_input>i5 12400f đi với main h610m hợp không</user_input>",
            '{"intent":"compatibility","target_product":null,"spec_detail":null,"cpu":"i5 12400f","mainboard":"h610m","gpu":null,"budget_amount":0,"category":null}',
        )
        + _example(
            "<system_hint>Handler = compatibility</system_hint>\n<user_input>ryzen 7 9800x3d + msi b850 pro + rtx 5070 ti có tương thích không?</user_input>",
            '{"intent":"compatibility","target_product":null,"spec_detail":null,"cpu":"ryzen 7 9800x3d","mainboard":"msi b850 pro","gpu":"rtx 5070 ti","budget_amount":0,"category":null}',
        )
    ),
    "suggestion": _example(
        "<system_hint>Handler = suggestion</system_hint>\n<user_input>mình có ryzen 5 7600, gợi ý main phù hợp</user_input>",
        '{"intent":"suggestion","target_product":null,"spec_detail":null,"cpu":"ryzen 5 7600","mainboard":null,"gpu":null,"budget_amount":0,"category":"mainboard"}',
    ),
    "price": (
        _example(
            "<system_hint>Handler = price</system_hint>\n<user_input>RTX 4080 Super giá bao nhiêu</user_input>",
            '{"intent":"price","target_product":"RTX 4080 Super","spec_detail":null,"cpu":null,"mainboard":null,"gpu":"RTX 4080 Super","budget_amount":0,"category":"gpu"}',
        )
        + _example(
            "<system_hint>Handler = price</system_hint>\n<user_input>i5 12400f và h610m tổng bao nhiêu</user_input>",
            '{"intent":"price","target_product":null,"spec_detail":null,"cpu":"i5 12400f","mainboard":"h610m","gpu":null,"budget_amount":0,"category":null}',
        )
    ),
    "specification": (
        _example(
            "<system_hint>Handler = specification</system_hint>\n<user_input>RTX 4070 có bao nhiêu VRAM</user_input>",
            '{"intent":"specification","target_product":"RTX 4070","spec_detail":"vram","cpu":null,"mainboard":null,"gpu":"RTX 4070","budget_amount":0,"category":"gpu"}',
        )
        + _example(
            "<system_hint>Handler = specification</system_hint>\n<user_input>RTX 3080 chơi PUBG mượt không</user_input>",
            '{"intent":"specification","target_product":"RTX 3080","spec_detail":"chơi PUBG mượt","cpu":null,"mainboard":null,"gpu":"RTX 3080","budget_amount":0,"category":"gpu"}',
        )
    ),
    "product_search": (
        _example(
            "<system_hint>Handler = product_search</system_hint>\n<user_input>tìm cho mình SSD Samsung</user_input>",
            '{"intent":"product_search","target_product":"Samsung","spec_detail":null,"cpu":null,"mainboard":null,"gpu":null,"budget_amount":0,"category":"ssd"}',
        )
        + _example(
            "<system_hint>Handler = product_search</system_hint>\n<user_input>tư vấn card đồ họa tầm 8 triệu</user_input>",
            '{"intent":"product_search","target_product":null,"spec_detail":null,"cpu":null,"mainboard":null,"gpu":null,"budget_amount":8000000,"category":"gpu"}',
        )
    ),
    "combo_review": _example(
        "<system_hint>Handler = combo_review</system_hint>\n<user_input>đánh giá ryzen 5 7600, b650m và rtx 4070</user_input>",
        '{"intent":"combo_review","target_product":null,"spec_detail":null,"cpu":"ryzen 5 7600","mainboard":"b650m","gpu":"rtx 4070","budget_amount":0,"category":null}',
    ),
    "general_chat": _example(
        "<system_hint>Handler = general_chat</system_hint>\n<user_input>xin chào</user_input>",
        '{"intent":"general_chat","target_product":null,"spec_detail":null,"cpu":null,"mainboard":null,"gpu":null,"budget_amount":0,"category":null}',
    ),
}
