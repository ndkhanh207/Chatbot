from app.compatibility.compat_logic import check_cpu_gpu_compat, check_cpu_main_compat


def test_ryzen_7_7700x_b850_allows_one_tier_lower_mainboard():
    result = check_cpu_main_compat(
        {"name": "AMD Ryzen 7 7700X", "socket": "AM5"},
        {"name": "MSI B850 PRO B850M-VC WIFI6E AM5 DDR5 Micro ATX", "socket": "AM5"},
    )

    assert result["is_compatible"] is True
    assert result["main_tier"] == 2
    assert result["required_tier"] == 2


def test_cpu_gpu_balance_accounts_for_generation():
    old_gpu = check_cpu_gpu_compat(
        {"name": "AMD Ryzen 7 9800X3D"},
        {"name": "NVIDIA GeForce RTX 2070"},
    )
    current_gpu = check_cpu_gpu_compat(
        {"name": "AMD Ryzen 7 9800X3D"},
        {"name": "NVIDIA GeForce RTX 5070 Ti"},
    )

    assert old_gpu["warning"] and "thế hệ cũ" in old_gpu["warning"]
    assert old_gpu["cpu_generation"] == 5
    assert old_gpu["gpu_generation"] == 2
    assert current_gpu["warning"] is None
