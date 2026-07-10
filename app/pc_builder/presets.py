from app.pc_builder.constants import PURPOSE_KEYWORD_MAP

# Danh sách các cấu hình cài sẵn (Presets), dễ dàng mở rộng thêm
PRESET_CONFIGS = [
    {
        "id": "BUILD-06265",
        "budget": 10_000_000,
        "margin": 1_000_000,
        "purposes": ["office"],
        "cpu": "Intel Core i3-13100",
        "gpu": "Asus TUF GAMING OC Radeon RX 6500 XT 4GB GDDR6 Black",
        "mainboard": "ASRock Z690M PG RIPTIDE/D5 DDR5 Micro ATX",
        "reply": "[GỢI Ý BỘ PC TỐI ƯU]\n- Mã bộ: BUILD-06265\n\nXin chào, tôi rất vui được giúp bạn xây dựng một máy tính để làm văn phòng hiệu quả! Bạn muốn sử dụng bộ PC này cho văn phòng và có ngân sách khoảng ~10 triệu.\n\nBộ PC của bạn sẽ bao gồm các thành phần sau:\n\n- CPU: Intel Core i3-13100, giá ~3 triệu\n- GPU: Asus TUF GAMING OC Radeon RX 6500 XT 4GB GDDR6 Black, giá ~3.8 triệu\n- Mainboard: ASRock Z690M PG RIPTIDE/D5 DDR5 Micro ATX, giá ~3.2 triệu\n- Phí lắp ráp: ~0.2 triệu\n\nTổng cộng chi phí cho các thành phần này là khoảng ~10.2 triệu."
    },
    {
        "id": "BUILD-08755",
        "budget": 15_000_000,
        "margin": 1_000_000,
        "purposes": ["game", "esport"],
        "cpu": "AMD Ryzen 7 7700X",
        "gpu": "Asus TUF GAMING OC Radeon RX 6500 XT 4GB GDDR6 Black",
        "mainboard": "MSI B850 PRO B850M-VC WIFI6E AM5 DDR5 Micro ATX",
        "reply": "[GỢI Ý BỘ PC TỐI ƯU]\n- Mã bộ: BUILD-08755\n\nXin chào, tôi rất vui được giúp bạn xây dựng một máy tính để chơi game hiệu quả! Bạn muốn sử dụng bộ PC này cho chơi game và có ngân sách khoảng ~15 triệu.\n\nBộ PC của bạn sẽ bao gồm các thành phần sau:\n\n- CPU: AMD Ryzen 7 7700X, giá ~5.8 triệu\n- GPU: Asus TUF GAMING OC Radeon RX 6500 XT 4GB GDDR6 Black, giá ~3.8 triệu\n- Mainboard: MSI B850 PRO B850M-VC WIFI6E AM5 DDR5 Micro ATX, giá ~5 triệu\n- Phí lắp ráp: ~0.2 triệu\n\nTổng cộng chi phí cho các thành phần này là khoảng ~14.9 triệu."
    },
    {
        "id": "BUILD-PROG-15",
        "budget": 15_000_000,
        "margin": 1_000_000,
        "purposes": ["programming"],
        "cpu": "Intel Core i5-13400F",
        "gpu": "GTX 1650 4GB",
        "mainboard": None,
        "reply": "[GỢI Ý BỘ PC TỐI ƯU]\n- Mã bộ: BUILD-PROG-15\n\nXin chào, bộ PC này được thiết kế tối ưu cho lập trình (Java, Web, Mobile) với ngân sách 15 triệu.\n\n- CPU: Intel Core i5-13400F\n- RAM: 32GB (rất quan trọng khi chạy máy ảo/Docker)\n- SSD: 1TB NVMe\n- GPU: GTX 1650 4GB (đủ xuất hình và xử lý nhẹ)\n- Phí lắp ráp: ~0.2 triệu\n\nTổng chi phí: ~15 triệu."
    },
    {
        "id": "BUILD-02021",
        "budget": 20_000_000,
        "margin": 1_000_000,
        "purposes": ["game", "office", "programming"],
        "cpu": "AMD Ryzen 9 7950X",
        "gpu": "Asus TUF GAMING OC Radeon RX 6500 XT 4GB GDDR6 Black",
        "mainboard": "ASRock B850 Pro RS WiFi AM5 DDR5 ATX",
        "reply": "[GỢI Ý BỘ PC TỐI ƯU]\n- Mã bộ: BUILD-02021\n\nXin chào, tôi rất vui được giúp bạn xây dựng một máy tính để sử dụng hiệu quả! Bạn muốn sử dụng bộ PC này cho sử dụng và có ngân sách khoảng ~20 triệu.\n\nBộ PC của bạn sẽ bao gồm các thành phần sau:\n\n- CPU: AMD Ryzen 9 7950X, giá ~10.8 triệu\n- GPU: Asus TUF GAMING OC Radeon RX 6500 XT 4GB GDDR6 Black, giá ~3.8 triệu\n- Mainboard: ASRock B850 Pro RS WiFi AM5 DDR5 ATX, giá ~5.3 triệu\n- Phí lắp ráp: ~0.2 triệu\n\nTổng cộng chi phí cho các thành phần này là khoảng ~20.1 triệu."
    },
    {
        "id": "BUILD-GAMING-25",
        "budget": 25_000_000,
        "margin": 1_000_000,
        "purposes": ["game"],
        "cpu": "AMD Ryzen 5 7600",
        "gpu": "RTX 4060 Ti 8GB",
        "mainboard": "B650M",
        "reply": "[GỢI Ý BỘ PC TỐI ƯU]\n- Mã bộ: BUILD-GAMING-25\n\nCấu hình 25 triệu cực kỳ ngon cho nhu cầu Gaming Mid-range (chiến mượt các game AAA ở 2K):\n\n- CPU: AMD Ryzen 5 7600\n- GPU: RTX 4060 Ti 8GB\n- Mainboard: B650M\n- RAM: 32GB DDR5\n- Tổng chi phí: ~25.2 triệu."
    },
    {
        "id": "BUILD-EDIT-25",
        "budget": 25_000_000,
        "margin": 1_000_000,
        "cpu": "Intel Core i5-13600K",
        "gpu": "RTX 3060 12GB",
        "mainboard": "B760M",
        "purposes": ["video editing", "render", "đồ họa"],
        "reply": "[GỢI Ý BỘ PC TỐI ƯU]\n- Mã bộ: BUILD-EDIT-25\n\nCấu hình 25 triệu tối ưu nhất cho Video Editing (Premiere, DaVinci, After Effects):\n\n- CPU: Intel Core i5-13600K (hỗ trợ QuickSync render cực nhanh)\n- GPU: RTX 3060 12GB (VRAM lớn cho edit video)\n- Mainboard: B760M\n- RAM: 32GB DDR5\n- Tổng chi phí: ~25.5 triệu."
    },
    {
        "id": "BUILD-08908",
        "budget": 30_000_000,
        "margin": 1_000_000,
        "purposes": ["game aaa"],
        "cpu": "Intel Core i9-13900K",
        "gpu": "Asus TUF GAMING OC Radeon RX 7800 XT 16GB GDDR6 White",
        "mainboard": "ASUS B760M-AYW WIFI D4",
        "reply": "[GỢI Ý BỘ PC TỐI ƯU]\n- Mã bộ: BUILD-08908\n\nXin chào, tôi rất vui được giúp bạn xây dựng một máy tính để chơi game aaa hiệu quả! Bạn muốn sử dụng bộ PC này cho chơi game aaa và có ngân sách khoảng ~30 triệu.\n\nBộ PC của bạn sẽ bao gồm các thành phần sau:\n\n- CPU: Intel Core i9-13900K, giá ~10.4 triệu\n- GPU: Asus TUF GAMING OC Radeon RX 7800 XT 16GB GDDR6 White, giá ~14.4 triệu\n- Mainboard: ASUS B760M-AYW WIFI D4, giá ~4.9 triệu\n- Phí lắp ráp: ~0.2 triệu\n\nTổng cộng chi phí cho các thành phần này là khoảng ~29.9 triệu."
    },
    {
        "id": "BUILD-AAA-40",
        "budget": 40_000_000,
        "margin": 2_000_000,
        "purposes": ["game aaa"],
        "cpu": "AMD Ryzen 7 7800X3D",
        "gpu": "RTX 4070 Ti SUPER 16GB",
        "mainboard": "X670E",
        "reply": "[GỢI Ý BỘ PC TỐI ƯU]\n- Mã bộ: BUILD-AAA-40\n\nCấu hình 40 triệu cao cấp chiến mượt mọi game AAA max setting:\n\n- CPU: AMD Ryzen 7 7800X3D (Vua gaming)\n- GPU: RTX 4070 Ti SUPER 16GB\n- Mainboard: X670E\n- RAM: 32GB DDR5\n- Tổng chi phí: ~40.5 triệu."
    },
    {
        "id": "BUILD-08333",
        "budget": 50_000_000,
        "margin": 1_000_000,
        "cpu": "Intel Core i3-13100",
        "gpu": "MSI GAMING TRIO GeForce RTX 4080 16GB GDDR6X Black",
        "mainboard": "ASRock Z690M PG RIPTIDE/D5 DDR5 Micro ATX",
        "purposes": ["design", "ai", "render", "đồ họa"],
        "reply": "[GỢI Ý BỘ PC TỐI ƯU]\n- Mã bộ: BUILD-08333\n\nXin chào, tôi rất vui được giúp bạn xây dựng một máy tính để ai hiệu quả! Bạn muốn sử dụng bộ PC này cho ai và có ngân sách khoảng ~50 triệu.\n\nBộ PC của bạn sẽ bao gồm các thành phần sau:\n\n- CPU: Intel Core i3-13100, giá ~3 triệu\n- GPU: MSI GAMING TRIO GeForce RTX 4080 16GB GDDR6X Black, giá ~44.4 triệu\n- Mainboard: ASRock Z690M PG RIPTIDE/D5 DDR5 Micro ATX, giá ~3.2 triệu\n- Phí lắp ráp: ~0.3 triệu\n\nTổng cộng chi phí cho các thành phần này là khoảng ~50.9 triệu."
    }
]

def get_preset_by_id(build_id: str) -> dict | None:
    if not build_id:
        return None
    build_id = build_id.upper()
    return next((preset for preset in PRESET_CONFIGS if preset["id"].upper() == build_id), None)


def get_preset_reply(budget: int, purpose_str: str, brand_filter: dict, component_filter: dict) -> dict | None:
    """
    Trả về câu trả lời cài sẵn nếu match đúng Ngân sách và Mục đích.
    Dễ dàng mở rộng thêm bằng cách thêm dict vào list PRESET_CONFIGS.
    """
    if budget is None:
        return None
        
    # Bỏ qua preset nếu người dùng chỉ định rõ linh kiện/hãng
    has_specific_component = bool(component_filter and (component_filter.get('cpu_model') or component_filter.get('gpu_model')))
    has_specific_brand = bool(brand_filter and (brand_filter.get('cpu_brand') or brand_filter.get('gpu_brand')))
    if has_specific_component or has_specific_brand:
        return None

    msg_lower = purpose_str.lower()
    
    # Xác định các mục đích từ tin nhắn người dùng dựa vào hằng số PURPOSE_KEYWORD_MAP
    user_purposes = set()
    for purpose_key, keywords in PURPOSE_KEYWORD_MAP.items():
        if any(kw in msg_lower for kw in keywords):
            user_purposes.add(purpose_key)
            
    # Duyệt qua các preset xem có match không
    for preset in PRESET_CONFIGS:
        preset_budget = preset["budget"]
        margin = preset.get("margin", 1_000_000)
        
        # Kiểm tra ngân sách có nằm trong khoảng sai số không
        if abs(budget - preset_budget) <= margin:
            preset_purposes = set(preset["purposes"])
            # Khớp nếu người dùng không có mục đích cụ thể (chỉ hỏi budget) 
            # hoặc có mục đích trùng khớp với mục đích của preset
            if not user_purposes or user_purposes.intersection(preset_purposes):
                print(f"⚠️ [PRESET] Đã khớp cấu hình cài sẵn: {preset['id']} (Ngân sách: {preset_budget})")
                return preset

    return None
