from app.utils.common import normalize_text

COMPATIBILITY_TRIGGERS = [
    'tương thích', 'lắp được', 'chạy được', 'hợp không', 'đi cùng', 'đi với', 'vừa không', 'cắm được'
]
CPU_TERMS = ['cpu', 'vi xử lý', 'i3', 'i5', 'i7', 'i9', 'ryzen']
GPU_TERMS = ['gpu', 'vga', 'card', 'đồ họa', 'rtx', 'gtx', 'rx']
MAIN_TERMS = ['bo mạch chủ', 'motherboard', 'h610', 'b760', 'z790', 'x670', 'a520']


def is_compatibility_query(message):
    return any(term in message for term in COMPATIBILITY_TRIGGERS)


def _get_compatibility_description(compatibility_rules):
    if compatibility_rules is None or compatibility_rules.empty:
        return 'phải có cùng thế hệ socket mới có thể tương thích'

    # Tìm rule theo cả 2 chiều thứ tự cột (component_1/component_2),
    # tránh trường hợp data lưu ngược (motherboard, cpu) làm fallback sai.
    rule_row = compatibility_rules[
        ((compatibility_rules['component_1'] == 'cpu') &
         (compatibility_rules['component_2'] == 'motherboard')) |
        ((compatibility_rules['component_1'] == 'motherboard') &
         (compatibility_rules['component_2'] == 'cpu'))
    ]
    if rule_row.empty:
        return 'phải có cùng thế hệ socket mới có thể tương thích'

    return str(rule_row.iloc[0].get('description', '')).strip()


def build_compatibility_context(user_message, knowledge_base, compatibility_rules, search_fn):
    if not user_message:
        return ''

    msg_lower = normalize_text(user_message)
    if not is_compatibility_query(msg_lower):
        return ''

    # 1. Nhận diện các thực thể có trong câu hỏi dựa trên từ khóa
    has_cpu = any(term in msg_lower for term in CPU_TERMS)
    has_gpu = any(term in msg_lower for term in GPU_TERMS)
    has_main = any(term in msg_lower for term in MAIN_TERMS)

    compatibility_context = ''

    # ==========================================================
    # LUỒNG 1: KIỂM TRA CPU + MAINBOARD (SOCKET MATCH)
    # CHỈ CHẠY KHI USER THỰC SỰ ĐỀ CẬP ĐẾN CPU TRONG CÂU HỎI
    # ==========================================================
    if has_cpu and has_main:
        best_cpu = search_fn(user_message, 'CPU', 1)
        best_main = search_fn(user_message, 'MAINBOARD', 1)

        if best_cpu and best_main:
            cpu = best_cpu[0]
            main = best_main[0]

            # Lấy trường socket (hỗ trợ cả chữ hoa/thường tùy file CSV)
            cpu_socket = str(cpu.get('socket_type', cpu.get('socket', cpu.get('Socket', '')))).strip().upper()
            main_socket = str(main.get('socket_type', main.get('socket', main.get('Socket', '')))).strip().upper()

            cpu_name = cpu.get('tên', cpu.get('name', cpu.get('CPU_Model', '')))
            # FIX: fallback tên mainboard phải lấy từ dict `main`, không phải `cpu`
            main_name = main.get('tên', main.get('name', main.get('Motherboard_Model', '')))
            rule_desc = _get_compatibility_description(compatibility_rules)

            if cpu_socket and main_socket:
                if cpu_socket == main_socket:
                    compatibility_context += (
                        f"[KẾT LUẬN THẨM ĐỊNH KỸ THUẬT: TƯƠNG THÍCH HOÀN HẢO]\n"
                        f"- Linh kiện: CPU '{cpu_name}' và Bo mạch chủ '{main_name}'\n"
                        f"- Trạng thái: Khớp Socket {cpu_socket} với nhau.\n"
                        f"- Yêu cầu AI: Khẳng định chắc chắn 100% combo CPU và Mainboard này lắp đặt hoàn hảo. Cấm bảo người dùng đi tự kiểm tra lại.\n\n"
                    )
                else:
                    # Tìm kiếm phương án thay thế tự động từ kho hàng
                    alt_mains = search_fn(f"mainboard socket {cpu_socket}", 'MAINBOARD', 2)
                    alt_main_names = [m.get('tên', m.get('name', m.get('Motherboard_Model', ''))) for m in alt_mains] if alt_mains else []

                    compatibility_context += (
                        f"[KẾT LUẬN THẨM ĐỊNH KỸ THUẬT: LỖI NGHIÊM TRỌNG - KHÔNG TƯƠNG THÍCH VẬT LÝ]\n"
                        f"- Lỗi: CPU '{cpu_name}' dùng Socket {cpu_socket} không thể cắm vào Bo mạch chủ '{main_name}' dùng Socket {main_socket}.\n"
                        f"- Yêu cầu AI: Khẳng định KHÔNG THỂ LẮP ĐẶT, cảnh báo rủi ro gãy chân socket phần cứng. Sau đó bắt buộc gợi ý khách đổi sang dòng Mainboard hỗ trợ socket {cpu_socket} như: {', '.join(alt_main_names)}.\n\n"
                    )

    # ==========================================================
    # LUỒNG 2: KIỂM TRA GPU + MAINBOARD (PCIE MATCH)
    # CHẠY KHI CÓ GPU VÀ MAINBOARD, TUYỆT ĐỐI KHÔNG LIÊN QUAN ĐẾN SOCKET CPU
    # ==========================================================
    if has_gpu and has_main:
        best_gpu = search_fn(user_message, 'GPU', 1)
        best_main = search_fn(user_message, 'MAINBOARD', 1)

        if best_gpu and best_main:
            gpu = best_gpu[0]
            main = best_main[0]

            gpu_name = gpu.get('tên', gpu.get('name', gpu.get('GPU_Model', '')))
            # FIX: fallback tên mainboard phải lấy từ dict `main`, không phải `gpu`
            main_name = main.get('tên', main.get('name', main.get('Motherboard_Model', '')))

            # Tách biệt hoàn toàn context cho GPU: Tất cả GPU dùng khe PCIe x16 tiêu chuẩn
            compatibility_context += (
                f"[KẾT LUẬN THẨM ĐỊNH KỸ THUẬT: TƯƠNG THÍCH TIÊU CHUẨN]\n"
                f"- Linh kiện: Card đồ họa '{gpu_name}' và Bo mạch chủ '{main_name}'\n"
                f"- Trạng thái: Tương thích hoàn toàn qua giao tiếp PCI Express x16 tiêu chuẩn.\n"
                f"- Yêu cầu AI: Khẳng định chắc chắn 100% là LẮP VỪA VÀ CHẠY TỐT. Giải thích ngắn gọn cho khách hiểu tất cả card đồ họa hiện đại ngày nay đều dùng chung chuẩn khe cắm PCIe x16 nên không lo bất tương thích vật lý. Tuyệt đối nghiêm cấm đề cập đến từ 'Socket' hoặc 'RAM' trong câu trả lời này.\n\n"
            )
    return compatibility_context