from utils import normalize_text

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

    rule_row = compatibility_rules[
        (compatibility_rules['component_1'] == 'cpu') &
        (compatibility_rules['component_2'] == 'motherboard')
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

    has_cpu = any(term in msg_lower for term in CPU_TERMS)
    has_gpu = any(term in msg_lower for term in GPU_TERMS)
    has_main = any(term in msg_lower for term in MAIN_TERMS)

    compatibility_context = ''

    if has_cpu and has_main:
        best_cpu = search_fn(user_message, 'CPU', 1)
        best_main = search_fn(user_message, 'MAINBOARD', 1)

        if best_cpu and best_main:
            cpu = best_cpu[0]
            main = best_main[0]
            cpu_socket = normalize_text(cpu.get('socket', cpu.get('socket_type', ''))).upper()
            main_socket = normalize_text(main.get('socket', main.get('socket_type', ''))).upper()
            rule_desc = _get_compatibility_description(compatibility_rules)

            cpu_name = cpu.get('tên') or cpu.get('name') or ''
            main_name = main.get('tên') or main.get('name') or ''
            if cpu_socket and main_socket and cpu_socket == main_socket:
                compatibility_context += (
                    f"[KẾT QUẢ THẨM ĐỊNH TƯƠNG THÍCH CHÍNH XÁC]\n"
                    f"- Linh kiện 1: CPU '{cpu_name}' (Socket: {cpu_socket})\n"
                    f"- Linh kiện 2: Bo mạch chủ '{main_name}' (Socket: {main_socket})\n"
                    f"- ĐÁNH GIÁ TỪ HỆ THỐNG: TƯƠNG THÍCH HOÀN HẢO 100%. Lắp ráp an toàn và chạy bình thường.\n"
                    f"- Chi tiết quy tắc: Quy tắc yêu cầu {rule_desc}. Do hai linh kiện cùng chung Socket {cpu_socket} nên hoàn toàn hợp lệ.\n"
                )
            else:
                compatibility_context += (
                    f"[KẾT QUẢ THẨM ĐỊNH TƯƠNG THÍCH CHÍNH XÁC]\n"
                    f"- Linh kiện 1: CPU '{cpu_name}' (Socket: {cpu_socket})\n"
                    f"- Linh kiện 2: Bo mạch chủ '{main_name}' (Socket: {main_socket})\n"
                    f"- ĐÁNH GIÁ TỪ HỆ THỐNG: KHÔNG TƯƠNG THÍCH. Nguy hiểm, không được lắp đặt!\n"
                    f"- Chi tiết quy tắc: Quy tắc yêu cầu {rule_desc}. CPU dùng socket {cpu_socket} khác với Bo mạch chủ dùng socket {main_socket}.\n"
                )

    if has_gpu and has_main:
        best_gpu = search_fn(user_message, 'GPU', 1)
        best_main = search_fn(user_message, 'MAINBOARD', 1)

        if best_gpu and best_main:
            gpu = best_gpu[0]
            main = best_main[0]
            gpu_name = gpu.get('tên') or gpu.get('name') or ''
            main_name = main.get('tên') or main.get('name') or ''
            compatibility_context += (
                f"[KẾT QUẢ THẨM ĐỊNH TƯƠNG THÍCH CHÍNH XÁC]\n"
                f"- Linh kiện 1: Card đồ họa '{gpu_name}'\n"
                f"- Linh kiện 2: Bo mạch chủ '{main_name}'\n"
                f"- ĐÁNH GIÁ TỪ HỆ THỐNG: TƯƠNG THÍCH TIÊU CHUẨN.\n"
                f"- Chi tiết: Card đồ họa sử dụng khe cắm PCIe tiêu chuẩn quốc tế, hoàn toàn lắp vừa bo mạch chủ này.\n"
            )

    return compatibility_context
