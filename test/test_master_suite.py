import os
import sys
import subprocess
import pytest

# Tự động chèn tuyệt đối thư mục gốc project vào đầu danh sách sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

TEST_MODULES = [
    "test/test_specification.py",
    "test/test_compatibility.py",
    "test/test_pc_builder_api.py",
    "test/test_price_check.py",
    "test/test_knowledge_base_api.py",
    "test/test_restful_chat_api.py"
]

@pytest.mark.parametrize("test_file", TEST_MODULES)
def test_master_submodule_execution(test_file):
    """Thực thi độc lập từng file test thông qua tiến trình con (subprocess) để đảm bảo cách ly môi trường tuyệt đối."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    full_path = os.path.join(root_dir, test_file)
    
    assert os.path.exists(full_path), f"Không tìm thấy file kiểm thử: {full_path}"
    
    # Kích hoạt tiến trình pytest độc lập cho từng module bằng sys.executable
    cmd = [sys.executable, "-m", "pytest", full_path, "-v", "-s"]
    
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    print(f"\n=== [MASTER SUITE] Khởi chạy kiểm thử: {test_file} ===")
    result = subprocess.run(cmd, cwd=root_dir, capture_output=True, text=True, encoding='utf-8', env=env)
    
    # In toàn bộ log của sub-test ra console
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
        
    assert result.returncode == 0, f"Kiểm thử thất bại tại module: {test_file}"

if __name__ == "__main__":
    # Hỗ trợ chạy trực tiếp bằng lệnh: python test/test_master_suite.py
    print("=== 🚀 KÍCH HOẠT HỆ THỐNG KIỂM THỬ TỔNG THỂ (MASTER TEST SUITE) ===")
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    exit_code = pytest.main([__file__, "-v", "-s"])
    sys.exit(exit_code)
