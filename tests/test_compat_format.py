from app.compatibility.compat_format import _fmt_component_combo


def test_combo_context_marks_7700x_4080_compatible_with_requirements():
    context = _fmt_component_combo(
        {"name": "AMD Ryzen 7 7700X", "price": 5831520},
        {"name": "MSI B850 PRO B850M-VC WIFI6E AM5 DDR5 Micro ATX", "price": 4992114},
        {"name": "MSI GAMING TRIO GeForce RTX 4080 16GB GDDR6X Black", "price": 44399760, "tdp": 320},
        {
            "is_compatible": True,
            "chipset": "B850",
            "reasons": ["Socket khớp (AM5), mainboard chipset B850 đủ gánh CPU."],
        },
        {"is_compatible": True, "gpu_pcie_gen": None, "main_pcie_gen": 4.0, "warning": None},
        {"is_compatible": True, "cpu_tier": 3, "gpu_tier": 4, "warning": None},
    )

    assert "TƯƠNG THÍCH" in context
    assert "không thấy cảnh báo nghẽn" in context
    assert "BOTTLENECK" not in context
    assert "RAM:" not in context
    assert "PSU" not in context
