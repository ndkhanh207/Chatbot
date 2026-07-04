_SYSTEM_CLASSIFY = (
    "Bạn là MÁY PHÂN LOẠI Ý ĐỊNH (Intent Classifier) nội bộ, KHÔNG PHẢI CHATBOT GIAO TIẾP VỚI KHÁCH.\n"
    "Nhiệm vụ của bạn là đọc câu hỏi và trả về đúng 1 ý định (intent) duy nhất dựa vào các luật sau.\n"
    "LƯU Ý QUAN TRỌNG VỀ NGỮ CẢNH: Nếu câu hỏi dùng đại từ (nó, con này...) hoặc bị thiếu chủ ngữ "
    "(VD: 'giá bao nhiêu?', 'xung cơ bản là mấy?'), bạn PHẢI đọc LỊCH SỬ HỘI THOẠI để ngầm hiểu khách đang nói về linh kiện nào.\n"
    "LƯU Ý VỀ TRẢ LỜI NGẮN: Nếu lịch sử cho thấy AI vừa hỏi ngân sách hoặc mục đích, và khách trả lời "
    "bằng 1 con số (VD: '20', '30') hoặc 1 mục đích ngắn (VD: 'chơi game', 'văn phòng'), đó là tiếp tục "
    "cuộc tư vấn build_pc — KHÔNG phải 'none' hay 'budget_search'.\n"
    "LƯU Ý VỀ HỎI TIẾP: Nếu khách hỏi tiếp tục chủ đề cũ cho 1 linh kiện khác (VD: 'thế còn rtx 4070 thì sao?', 'i5 12400f thì sao?'), HÃY GIỮ NGUYÊN Ý ĐỊNH CỦA CÂU HỎI TRƯỚC ĐÓ trong lịch sử.\n"
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
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU=i5 12400f, MAINBOARD=h610m, LAST_INTENT=compatibility\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: i5 12400f đi với h610m được không\nAI: Dạ được\n\n<user_input>thế còn main b760m thì sao?</user_input>"},
    {"role": "assistant", "content": '{"intent": "compatibility"}'},
    # ── Suggestion ──
    {"role": "user", "content": "<user_input>tôi có cpu ryzen 9 9950x3d rồi, tìm gpu phù hợp</user_input>"},
    {"role": "assistant", "content": '{"intent": "suggestion"}'},
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU=i9 14900k, LAST_INTENT=suggestion\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tìm main cho i9 14900k\nAI: Dạ anh có thể dùng Z790\n\n<user_input>thế còn tìm gpu thì sao</user_input>"},
    {"role": "assistant", "content": '{"intent": "suggestion"}'},
    # ── Price calculation ──
    {"role": "user", "content": "<user_input>tôi lấy main asus z790 và i9 14900k tổng bao nhiêu</user_input>"},
    {"role": "assistant", "content": '{"intent": "price_calculation"}'},
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU=i9 14900k, MAINBOARD=asus z790, LAST_INTENT=price_calculation\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: i9 14900k và asus z790 tổng bao nhiêu\nAI: Dạ tổng 20 triệu\n\n<user_input>nếu đổi main sang msi z790 thì tổng bao nhiêu</user_input>"},
    {"role": "assistant", "content": '{"intent": "price_calculation"}'},
    # ── Specification ──
    {"role": "user", "content": "<user_input>ryzen 7 7700x dùng socket nào vậy shop</user_input>"},
    {"role": "assistant", "content": '{"intent": "specification"}'},
    {"role": "user", "content": "<user_input>card msi rtx 5070 ti này thiết kế màu gì thế shop</user_input>"},
    {"role": "assistant", "content": '{"intent": "specification"}'},
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nGPU=rtx 4090, LAST_INTENT=price_check\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: rtx 4090 giá bao nhiêu\nAI: Dạ 50 triệu\n\n<user_input>Nó có mấy gb vram</user_input>"},
    {"role": "assistant", "content": '{"intent": "specification"}'},
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nGPU=rtx 3060 ti, LAST_INTENT=specification\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: rtx 3060 ti vram bao nhiêu\nAI: Dạ 8GB\n\n<user_input>thế còn rtx 4070 thì sao?</user_input>"},
    {"role": "assistant", "content": '{"intent": "specification"}'},
    # ── Price check ──
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU=i9 14900k, LAST_INTENT=suggestion\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tìm main cho i9 14900k\nAI: Dạ Z790\n\n<user_input>giá bao nhiêu</user_input>"},
    {"role": "assistant", "content": '{"intent": "price_check"}'},
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nGPU=rtx 3060 ti, LAST_INTENT=price_check\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: rtx 3060 ti giá bao nhiêu\nAI: Dạ 10 triệu\n\n<user_input>thế còn rx 6600 thì sao?</user_input>"},
    {"role": "assistant", "content": '{"intent": "price_check"}'},
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nGPU=rx 7600, LAST_INTENT=price_check\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: rx 7600 thì sao\nAI: Giá là 6.5 triệu\n\n<user_input>thế còn i9 14900k?</user_input>"},
    {"role": "assistant", "content": '{"intent": "price_check"}'},
    {"role": "user", "content": "<user_input>con vga rtx 4080 super giá nhiêu shop</user_input>"},
    {"role": "assistant", "content": '{"intent": "price_check"}'},
    # ── Budget search (1 linh kiện) ──
    {"role": "user", "content": "<user_input>tư vấn em con card đồ họa tầm 8 triệu</user_input>"},
    {"role": "assistant", "content": '{"intent": "budget_search"}'},
    {"role": "user", "content": "<user_input>tìm cpu tầm 3 triệu</user_input>"},
    {"role": "assistant", "content": '{"intent": "budget_search"}'},
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCATEGORY=gpu, LAST_INTENT=general_search\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tìm cho mình card đồ họa nvidia\nAI: Dạ bên em có nhiều mẫu\n\n<user_input>có loại nào tầm 10 triệu không?</user_input>"},
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
    {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCATEGORY=ram, LAST_INTENT=general_search\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: có loại ram ddr5 nào không\nAI: Dạ bên em có nhiều mẫu\n\n<user_input>thế còn của hãng corsair thì sao?</user_input>"},
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
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU=i5 12400f, MAINBOARD=h610m, LAST_INTENT=compatibility\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: i5 12400f đi với h610m được không\nAI: Dạ được\n\n<user_input>thế còn main b760m thì sao?</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Đổi mainboard, kế thừa CPU và ý định tương thích từ trạng thái đã xác nhận.", "intent": "compatibility", "target_product": "none", "spec_detail": "none", "cpu": "i5 12400f", "mainboard": "b760m", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU=ryzen 7 7800x3d, MAINBOARD=b650m, LAST_INTENT=compatibility\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: 7800x3d lắp với b650m ổn không\nAI: Dạ ổn\n\n<user_input>thế đi với con x670e thì sao</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Đổi mainboard sang x670e, kế thừa CPU từ context.", "intent": "compatibility", "target_product": "none", "spec_detail": "none", "cpu": "ryzen 7 7800x3d", "mainboard": "x670e", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "suggestion": [
        {"role": "user", "content": "<user_input>tôi có cpu ryzen 9 9950x3d rồi, tìm gpu phù hợp</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Đã có 1 linh kiện, tìm linh kiện khác -> suggestion.", "intent": "suggestion", "target_product": "none", "spec_detail": "none", "cpu": "ryzen 9 9950x3d", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "gpu"}'},
        {"role": "user", "content": "<user_input>tìm giúp tôi bo mạch chủ phù hợp cho CPU AMD Ryzen 7 7700X</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Đã có 1 linh kiện, tìm linh kiện khác -> suggestion.", "intent": "suggestion", "target_product": "none", "spec_detail": "none", "cpu": "amd ryzen 7 7700x", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "mainboard"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU=i9 14900k, LAST_INTENT=suggestion\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tìm main cho i9 14900k\nAI: Dạ anh có thể dùng Z790\n\n<user_input>thế còn tìm gpu thì sao</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Kế thừa CPU từ context, tìm GPU.", "intent": "suggestion", "target_product": "none", "spec_detail": "none", "cpu": "i9 14900k", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "gpu"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nGPU=rtx 4070, LAST_INTENT=suggestion\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tư vấn gpu rtx 4070\nAI: Dạ đây là các mẫu\n\n<user_input>tìm bo mạch chủ cho nó</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Kế thừa GPU từ context, tìm Mainboard.", "intent": "suggestion", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "rtx 4070", "budget_amount": 0, "category": "mainboard"}'},
    ],
    "price_calculation": [
        {"role": "user", "content": "<user_input>tôi lấy main asus z790 và i9 14900k tổng bao nhiêu</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Liệt kê nhiều linh kiện và hỏi tổng.", "intent": "price_calculation", "target_product": "none", "spec_detail": "none", "cpu": "i9 14900k", "mainboard": "asus z790", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU=i9 14900k, MAINBOARD=asus z790, LAST_INTENT=price_calculation\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: i9 14900k và asus z790 tổng bao nhiêu\nAI: Dạ tổng 20 triệu\n\n<user_input>nếu đổi main sang msi z790 thì tổng bao nhiêu</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Thay mainboard, kế thừa CPU.", "intent": "price_calculation", "target_product": "none", "spec_detail": "none", "cpu": "i9 14900k", "mainboard": "msi z790", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU=ryzen 5 7600x, GPU=rtx 4060, LAST_INTENT=price_calculation\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: ryzen 5 7600x và rtx 4060 giá nhiu\nAI: Dạ tổng là\n\n<user_input>thế nếu lấy cpu i5 12400f thì sao</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Thay CPU, kế thừa GPU.", "intent": "price_calculation", "target_product": "none", "spec_detail": "none", "cpu": "i5 12400f", "mainboard": "none", "gpu": "rtx 4060", "budget_amount": 0, "category": "none"}'},
    ],
    "specification": [
        {"role": "user", "content": "<user_input>ryzen 7 7700x dùng socket nào vậy shop</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi thông số socket của CPU.", "intent": "specification", "target_product": "ryzen 7 7700x", "spec_detail": "socket", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "<user_input>card msi rtx 5070 ti này thiết kế màu gì thế shop</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi thông số màu sắc của GPU.", "intent": "specification", "target_product": "msi rtx 5070 ti", "spec_detail": "màu", "cpu": "none", "mainboard": "none", "gpu": "msi rtx 5070 ti", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: RTX 4090 giá bao nhiêu\nAI: Dạ giá 50 triệu\n\n<user_input>Nó có mấy gb vram</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi thông số (ẩn chủ ngữ).", "intent": "specification", "target_product": "rtx 4090", "spec_detail": "vram", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: RTX 3060 Ti chơi pubg mượt không\nAI: Dạ chiến mượt\n\n<user_input>vậy rtx 4070 thì sao</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi tiếp tục hiệu năng (mượt) cho GPU khác.", "intent": "specification", "target_product": "rtx 4070", "spec_detail": "mượt", "cpu": "none", "mainboard": "none", "gpu": "rtx 4070", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: i9 14900k xung cơ bản bao nhiêu\nAI: Dạ 3.2 GHz\n\n<user_input>thế còn i7 14700k thì sao</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Kế thừa thông số (xung cơ bản) từ câu hỏi trước cho CPU mới.", "intent": "specification", "target_product": "i7 14700k", "spec_detail": "xung cơ bản", "cpu": "i7 14700k", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "price_check": [
        {"role": "user", "content": "<user_input>con vga rtx 4080 super giá nhiêu shop</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Hỏi giá 1 linh kiện cụ thể.", "intent": "price_check", "target_product": "rtx 4080 super", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nGPU=rtx 3060 ti, LAST_INTENT=price_check\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: rtx 3060 ti giá bao nhiêu\nAI: Dạ 10 triệu\n\n<user_input>thế còn rx 6600 thì sao?</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Kế thừa ý định kiểm tra giá cho GPU mới.", "intent": "price_check", "target_product": "rx 6600", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "rx 6600", "budget_amount": 0, "category": "none"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nGPU=rx 7600, LAST_INTENT=price_check\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: rx 7600 thì sao\nAI: Giá là 6.5 triệu\n\n<user_input>thế còn i9 14900k?</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Kế thừa ý định kiểm tra giá cho linh kiện mới.", "intent": "price_check", "target_product": "i9 14900k", "spec_detail": "none", "cpu": "i9 14900k", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "none"}'},
    ],
    "budget_search": [
        {"role": "user", "content": "tư vấn em con card tầm 4 triệu"},
        {"role": "assistant", "content": '{"reasoning": "Tìm 1 linh kiện theo ngân sách.", "intent": "budget_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 4000000, "category": "gpu"}'},
        {"role": "user", "content": "tìm cpu tầm 3 triệu"},
        {"role": "assistant", "content": '{"reasoning": "Tìm 1 linh kiện theo ngân sách.", "intent": "budget_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 3000000, "category": "cpu"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCATEGORY=gpu, LAST_INTENT=general_search\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tìm cho mình card đồ họa nvidia\nAI: Dạ bên em có nhiều mẫu\n\n<user_input>có loại nào tầm 10 triệu không?</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Kế thừa danh mục GPU, hỏi ngân sách 10 triệu = 10000000.", "intent": "budget_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 10000000, "category": "none"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCATEGORY=cpu, LAST_INTENT=budget_search\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tư vấn cpu\nAI: Dạ bên em có\n\n<user_input>khoảng 5 củ có con nào không</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Kế thừa danh mục CPU, ngân sách 5 củ = 5000000.", "intent": "budget_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 5000000, "category": "none"}'},
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
        {"role": "user", "content": "có loại ram ddr5 nào không"},
        {"role": "assistant", "content": '{"reasoning": "Tìm kiếm chung chung loại linh kiện.", "intent": "general_search", "target_product": "none", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "ram"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCATEGORY=ram, LAST_INTENT=general_search\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: có loại ram ddr5 nào không\nAI: Dạ bên em có nhiều mẫu\n\n<user_input>thế còn của hãng corsair thì sao?</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Kế thừa category ram, thêm từ khóa hãng.", "intent": "general_search", "target_product": "corsair", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "ram"}'},
        {"role": "user", "content": "[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCATEGORY=mainboard, LAST_INTENT=general_search\n\nLỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: bo mạch chủ ddr5\nAI: Dạ bên em có\n\n<user_input>cho xem của asus đi</user_input>"},
        {"role": "assistant", "content": '{"reasoning": "Kế thừa category mainboard, thêm từ khóa hãng.", "intent": "general_search", "target_product": "asus", "spec_detail": "none", "cpu": "none", "mainboard": "none", "gpu": "none", "budget_amount": 0, "category": "mainboard"}'},
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
