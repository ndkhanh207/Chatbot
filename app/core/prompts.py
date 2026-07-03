_SYSTEM_CLASSIFY = (
    "Bạn là MÁY PHÂN LOẠI Ý ĐỊNH (Intent Classifier) nội bộ, KHÔNG PHẢI CHATBOT GIAO TIẾP VỚI KHÁCH.\n"
    "Nhiệm vụ của bạn là đọc câu hỏi và trả về đúng 1 ý định (intent) duy nhất dựa vào các luật sau.\n"
    "LƯU Ý QUAN TRỌNG VỀ NGỮ CẢNH: Nếu câu hỏi dùng đại từ (nó, con này...) hoặc bị thiếu chủ ngữ "
    "(VD: 'giá bao nhiêu?', 'xung cơ bản là mấy?'), bạn PHẢI đọc LỊCH SỬ HỘI THOẠI để ngầm hiểu khách đang nói về linh kiện nào.\n"
    "LƯU Ý VỀ TRẢ LỜI NGẮN: Nếu lịch sử cho thấy AI vừa hỏi ngân sách hoặc mục đích, và khách trả lời "
    "bằng 1 con số (VD: '20', '30') hoặc 1 mục đích ngắn (VD: 'chơi game', 'văn phòng'), đó là tiếp tục "
    "cuộc tư vấn build_pc — KHÔNG phải 'none' hay 'budget_search'.\n"
    "LUẬT PHÂN LOẠI TUYỆT ĐỐI (Strict Intent Mapping):\n"
    "- 'compatibility': Khách hỏi về TƯƠNG THÍCH, ĐỘ HỢP NHAU (từ khóa: 'có lắp được với', 'đi với', 'chạy chung', 'tương thích không'). "
    "Nếu câu hỏi có chứa 2 LINH KIỆN CỤ THỂ TRỞ LÊN, ĐÓ TUYỆT ĐỐI LÀ 'compatibility', KHÔNG BAO GIỜ là 'specification'.\n"
    "- 'suggestion': Khách CHỈ CÓ SẴN 1 LINH KIỆN và nhờ tìm 1 linh kiện MỚI (chưa biết tên) để ghép cùng. CHỈ CÓ 1 linh kiện cụ thể xuất hiện.\n"
    "- 'price_calculation': Khách liệt kê nhiều linh kiện và muốn tính TỔNG GIÁ tiền.\n"
    "- 'specification': Khách hỏi về THÔNG SỐ (số nhân, VRAM, điện năng, xung, socket, chuẩn...) của 1 linh kiện "
    "(linh kiện này có thể nằm trong Lịch sử hội thoại).\n"
    "- 'price_check': Khách hỏi GIÁ BÁN của 1 linh kiện cụ thể.\n"
    "- 'budget_search': Khách tìm MỘT LINH KIỆN ĐƠN LẺ (chỉ 1 món CPU, GPU, mainboard...) dựa trên NGÂN SÁCH/TẦM GIÁ. "
    "KHÁC VỚI 'build_pc': budget_search CHỈ DÀNH CHO 1 LINH KIỆN.\n"
    "- 'build_pc': Khách muốn tư vấn/lắp ráp BỘ PC TRỌN BỘ (thường chứa các từ khóa: 'build pc', 'bộ pc', 'cả máy', 'dàn máy', 'bộ máy'). "
    "Bao gồm cả: trả lời ngân sách/mục đích khi AI đang hỏi trong luồng tư vấn PC.\n"
    "- 'general_search': Khách tìm kiếm, hỏi mua, hoặc nhờ tư vấn chung chung về một loại linh kiện/sản phẩm.\n"
    "- 'none': Khách giao tiếp thông thường, hoặc hỏi ngoài lề."
)

_FEWSHOT_CLASSIFY = [
    # ── Compatibility ──
    {"role": "user", "content": "<user_input>Intel Core i9-14900K có lắp được với main MSI B850 PRO không</user_input>"},
    {"role": "assistant", "content": '{"intent": "compatibility"}'},
    # ── Suggestion ──
    {"role": "user", "content": "<user_input>tôi có cpu ryzen 9 9950x3d rồi, tìm gpu phù hợp</user_input>"},
    {"role": "assistant", "content": '{"intent": "suggestion"}'},
    # ── Price calculation ──
    {"role": "user", "content": "<user_input>tôi lấy main asus z790 và i9 14900k tổng bao nhiêu</user_input>"},
    {"role": "assistant", "content": '{"intent": "price_calculation"}'},
    # ── Specification ──
    {"role": "user", "content": "<user_input>ryzen 7 7700x dùng socket nào vậy shop</user_input>"},
    {"role": "assistant", "content": '{"intent": "specification"}'},
    {"role": "user", "content": "<user_input>card msi rtx 5070 ti này thiết kế màu gì thế shop</user_input>"},
    {"role": "assistant", "content": '{"intent": "specification"}'},
    {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: RTX 4090 giá bao nhiêu\nAI: Dạ giá 50 triệu\n\n<user_input>Nó có mấy gb vram</user_input>"},
    {"role": "assistant", "content": '{"intent": "specification"}'},
    # ── Price check ──
    {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: Tìm mainboard cho i9 14900K\nAI: Có dòng Z790.\n\n<user_input>giá bao nhiêu</user_input>"},
    {"role": "assistant", "content": '{"intent": "price_check"}'},
    {"role": "user", "content": "<user_input>con vga rtx 4080 super giá nhiêu shop</user_input>"},
    {"role": "assistant", "content": '{"intent": "price_check"}'},
    # ── Budget search (1 linh kiện) ──
    {"role": "user", "content": "<user_input>tư vấn em con card đồ họa tầm 8 triệu</user_input>"},
    {"role": "assistant", "content": '{"intent": "budget_search"}'},
    {"role": "user", "content": "<user_input>tìm cpu tầm 3 triệu</user_input>"},
    {"role": "assistant", "content": '{"intent": "budget_search"}'},
    # ── Build PC (cả bộ) ──
    {"role": "user", "content": "<user_input>build pc gaming tầm 30 triệu</user_input>"},
    {"role": "assistant", "content": '{"intent": "build_pc"}'},
    {"role": "user", "content": "<user_input>build cho tôi 1 bộ pc giá khoảng 20 triệu</user_input>"},
    {"role": "assistant", "content": '{"intent": "build_pc"}'},
    {"role": "user", "content": "<user_input>tư vấn cho tôi bộ pc để chơi game aaa</user_input>"},
    {"role": "assistant", "content": '{"intent": "build_pc"}'},
    {"role": "user", "content": "<user_input>muốn có một bộ máy để làm đồ họa</user_input>"},
    {"role": "assistant", "content": '{"intent": "build_pc"}'},
    # ── Build PC: trả lời ngắn khi AI đang hỏi ngân sách ──
    {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tư vấn cho tôi bộ pc để chơi game\nAI: Dạ để build bộ máy tối ưu, bạn dự định đầu tư khoảng bao nhiêu tiền ạ?\n\n<user_input>20</user_input>"},
    {"role": "assistant", "content": '{"intent": "build_pc"}'},
    {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tư vấn cho tôi bộ pc để chơi game\nAI: Dạ để build bộ máy tối ưu, bạn dự định đầu tư khoảng bao nhiêu tiền ạ?\n\n<user_input>20 triệu</user_input>"},
    {"role": "assistant", "content": '{"intent": "build_pc"}'},
    # ── Build PC: trả lời mục đích khi AI đang hỏi mục đích ──
    {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: build pc tầm 25 triệu\nAI: Dạ với ngân sách 25 triệu, bạn dùng máy chủ yếu để làm gì ạ?\n\n<user_input>chơi game</user_input>"},
    {"role": "assistant", "content": '{"intent": "build_pc"}'},
    {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: build pc tầm 25 triệu\nAI: Dạ với ngân sách 25 triệu, bạn dùng máy chủ yếu để làm gì ạ?\n\n<user_input>văn phòng thôi</user_input>"},
    {"role": "assistant", "content": '{"intent": "build_pc"}'},
    # ── General search ──
    {"role": "user", "content": "<user_input>tìm cho tôi ssd của samsung</user_input>"},
    {"role": "assistant", "content": '{"intent": "general_search"}'},
    # ── None ──
    {"role": "user", "content": "<user_input>chào shop, bạn là bot à</user_input>"},
    {"role": "assistant", "content": '{"intent": "none"}'},
]


# ==============================================================================
# PASS 2: EXTRACTION (SYSTEM PROMPT & FOCUSED FEWSHOTS)
# ==============================================================================

_SYSTEM_EXTRACT = (
    "Bạn là MÁY TRÍCH XUẤT THỰC THỂ (Entity Extractor) nội bộ. Ý định (intent) đã được phân loại.\n"
    "Nhiệm vụ của bạn là trích xuất CÁC THỰC THỂ từ câu hỏi của khách.\n\n"
    "QUY TẮC TRÍCH XUẤT:\n"
    "- Hãy đọc kỹ định nghĩa và mô tả (description) của từng trường dữ liệu được yêu cầu.\n"
    "- Điền 'none' hoặc 0 nếu không có thông tin.\n"
    "CẢNH BÁO: TRÍCH XUẤT CHÍNH XÁC TỪ KHÓA CỦA KHÁCH. Không tự ý ghép thêm hãng nếu khách không viết."
)

_FEWSHOT_BY_INTENT = {
    "compatibility": [
        {"role": "user", "content": "<user_input>Intel Core i9-14900K có lắp được với main MSI B850 PRO B850M-VC AM5 không</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Có 2 linh kiện cụ thể -> compatibility.", "intent": "compatibility", "target_product": "none", "spec_detail": "none", "cpu": "intel core i9-14900k", "mainboard": "msi b850 pro b850m-vc am5", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "<user_input>AMD Ryzen 7 9800X3D đi với GPU GIGABYTE GeForce RTX 5070 Ti GAMING 16G có ổn không</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Có 2 linh kiện cụ thể -> compatibility.", "intent": "compatibility", "target_product": "none", "spec_detail": "none", "cpu": "amd ryzen 7 9800x3d", "mainboard": "none", "gpu": "gigabyte geforce rtx 5070 ti gaming 16g", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "<user_input>GPU GIGABYTE GeForce RTX 5070 Ti GAMING 16G lắp với main ASUS B760M-AYW WIFI D4 có sao không</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Có 2 linh kiện cụ thể -> compatibility.", "intent": "compatibility", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "asus b760m-ayw wifi d4", "gpu": "gigabyte geforce rtx 5070 ti gaming 16g", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "<user_input>CPU i9 14900k có lắp được với ryzen 7 9800x3d không</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Tương thích 2 CPU -> logic vô lý.", "intent": "none", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "suggestion": [
        {"role": "user", "content": "<user_input>tôi có cpu ryzen 9 9950x3d rồi, tìm gpu phù hợp</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Đã có 1 linh kiện, tìm linh kiện khác -> suggestion.", "intent": "suggestion", "target_product": "none", "spec_detail": "none", "cpu": "ryzen 9 9950x3d", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "gpu"}'},
        {"role": "user", "content": "<user_input>tìm giúp tôi bo mạch chủ phù hợp cho CPU AMD Ryzen 7 7700X</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Đã có 1 linh kiện, tìm linh kiện khác -> suggestion.", "intent": "suggestion", "target_product": "none", "spec_detail": "none", "cpu": "amd ryzen 7 7700x", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "mainboard"}'},
    ],
    "price_calculation": [
        {"role": "user", "content": "<user_input>tôi lấy main asus z790 và i9 14900k tổng bao nhiêu</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Liệt kê nhiều linh kiện và hỏi tổng.", "intent": "price_calculation", "target_product": "none", "spec_detail": "none", "cpu": "i9 14900k", "mainboard": "asus z790", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "specification": [
        {"role": "user", "content": "<user_input>ryzen 7 7700x dùng socket nào vậy shop</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi thông số socket của CPU.", "intent": "specification", "target_product": "ryzen 7 7700x", "spec_detail": "socket", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "<user_input>card msi rtx 5070 ti này thiết kế màu gì thế shop</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi thông số màu sắc của GPU.", "intent": "specification", "target_product": "msi rtx 5070 ti", "spec_detail": "màu", "cpu": "none", "mainboard": "none", "gpu": "msi rtx 5070 ti", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: RTX 4090 giá bao nhiêu\nAI: Dạ giá 50 triệu\n\n<user_input>Nó có mấy gb vram</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi thông số (ẩn chủ ngữ).", "intent": "specification", "target_product": "rtx 4090", "spec_detail": "vram", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "price_check": [
        {"role": "user", "content": "<user_input>con vga rtx 4080 super giá nhiêu shop</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi giá 1 linh kiện cụ thể.", "intent": "price_check", "target_product": "rtx 4080 super", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "budget_search": [
        {"role": "user", "content": "tư vấn em con card tầm 4 triệu"},
        {"role": "assistant", "content": '{"reasoning": "Tìm 1 linh kiện theo ngân sách.", "intent": "budget_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 4000000, "category": "gpu"}'},
        {"role": "user", "content": "tìm cpu tầm 3 triệu"},
        {"role": "assistant", "content": '{"reasoning": "Tìm 1 linh kiện theo ngân sách.", "intent": "budget_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 3000000, "category": "cpu"}'},
    ],
    "build_pc": [
        # Case chuẩn
        {"role": "user", "content": "build pc gaming tầm 30 triệu"},
        {"role": "assistant", "content": '{"reasoning": "Tư vấn nguyên bộ máy.", "intent": "build_pc", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 30000000, "category": "none"}'},
        # Có mục đích, chưa có ngân sách
        {"role": "user", "content": "tư vấn cho tôi bộ pc để chơi game aaa"},
        {"role": "assistant", "content": '{"reasoning": "Tư vấn bộ máy có mục đích rõ, chưa có ngân sách.", "intent": "build_pc", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        # Trả lời ngắn — số thuần — sau khi AI hỏi ngân sách
        {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tư vấn cho tôi bộ pc để chơi game\nAI: Dạ để build bộ máy tối ưu, bạn dự định đầu tư khoảng bao nhiêu tiền ạ?\n\n<user_input>20</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Khách đang trả lời câu hỏi ngân sách, số 20 = 20 triệu VNĐ.", "intent": "build_pc", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 20000000, "category": "none"}'},
        # Trả lời "20 triệu" sau khi AI hỏi
        {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tư vấn cho tôi bộ pc để chơi game\nAI: Dạ để build bộ máy tối ưu, bạn dự định đầu tư khoảng bao nhiêu tiền ạ?\n\n<user_input>20 triệu</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Khách trả lời ngân sách 20 triệu.", "intent": "build_pc", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 20000000, "category": "none"}'},
        # Trả lời mục đích sau khi AI hỏi mục đích
        {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: build pc tầm 25 triệu\nAI: Dạ với ngân sách 25 triệu, bạn dùng máy chủ yếu để làm gì ạ?\n\n<user_input>chơi game</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Khách đang trả lời mục đích sử dụng trong luồng tư vấn PC.", "intent": "build_pc", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        # Muốn bộ máy mới kiểu tự nhiên
        {"role": "user", "content": "muốn có một bộ máy để làm đồ họa"},
        {"role": "assistant", "content": '{"reasoning": "Tư vấn bộ máy cho mục đích đồ họa.", "intent": "build_pc", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "general_search": [
        {"role": "user", "content": "tìm cho tôi ssd của samsung"},
        {"role": "assistant", "content": '{"reasoning": "Tìm kiếm chung chung.", "intent": "general_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "ssd"}'},
    ],
    "none": [
        {"role": "user", "content": "bạn là ai, bot à"},
        {"role": "assistant", "content": '{"reasoning": "Giao tiếp ngoài lề.", "intent": "none", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ]
}

_FALLBACK_MAP = {
    "specification": "compatibility",
    "build_pc": "compatibility",
    "compatibility": "suggestion",
    "price_calculation": "price_check"
}
