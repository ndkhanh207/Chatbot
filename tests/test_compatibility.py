import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from tests.utils import get_auth_headers
"""
Test riêng cho tính năng kiểm tra/gợi ý tương thích linh kiện
(CPU-MAINBOARD, GPU-MAINBOARD, CPU-GPU).

Tách biệt khỏi test_export_qa.py (spec search) — dùng report file
và session prefix riêng để 2 bộ test không lẫn dữ liệu vào nhau.
"""

import re
import pytest
from fastapi.testclient import TestClient
from main import app
from app.catalog import ShopCatalog
from config.config import Config

app.state.catalog = ShopCatalog.load(Config.PC_STORE_DATA)
client = TestClient(app)


API_URL = "/chat"
SESSION_API_BASE = "/sessions"
REPORT_FILE = "tests/reports/report_compatibility.md"

COMPAT_TEST_CASES = [
    # ─── CPU - MAINBOARD: socket khớp + tier đủ → tương thích ───
    ("compat_cpu_main_match",
     "AMD Ryzen 7 9800X3D có lắp được với main MSI B850 PRO không",
     [("tương thích", "phù hợp", "lắp được", "lắp vừa")]),

    # ─── CPU - MAINBOARD: socket KHÔNG khớp (LGA1700 vs AM5) ───
    ("compat_cpu_main_socket_mismatch",
     "Intel Core i9-14900K có lắp được với main MSI B850 PRO không",
     [("không tương thích", "không phù hợp", "không lắp được", "khác socket")]),

    # ─── CPU - MAINBOARD: socket khớp; không suy VRM/cấp điện từ tên chipset ───
   
    ("compat_cpu_main_tier_insufficient",
     "Intel Core i9-13900K có lắp được với main Asus H610 PRIME không",
     [("tương thích", "phù hợp", "lắp được")]),

    # ─── GPU - MAINBOARD: PCIe gen lệch → vẫn tương thích, có cảnh báo băng thông ───
    ("compat_gpu_main_pcie_warning",
     "GPU GIGABYTE GeForce RTX 5070 Ti GAMING 16G lắp với main ASUS PRIME H610M-K D4 có sao không",
     ["tương thích", ("băng thông", "pcie 4.0", "không phát huy", "thấp hơn")]),

    # ─── CPU - GPU: tier cân đối → không cảnh báo nghẽn ───
    ("compat_cpu_gpu_balanced",
     "AMD Ryzen 7 9800X3D đi với GPU GIGABYTE GeForce RTX 5070 Ti GAMING 16G có ổn không",
     [("phù hợp", "ổn", "tương thích")]),

    # ─── CPU + MAINBOARD + GPU: kiểm tra đủ 3 cạnh tương thích ───
    ("compat_cpu_main_gpu_combo",
     "AMD Ryzen 7 9800X3D + MSI B850 PRO B850M-VC WIFI6E AM5 DDR5 Micro ATX + GIGABYTE GeForce RTX 5070 Ti GAMING 16G có tương thích với nhau không?",
     ["9800x3d", "b850", "rtx 5070 ti", ("tương thích", "phù hợp"), ("cpu", "mainboard"), ("gpu", "pcie")]),

    # ─── CPU - GPU: không có ràng buộc vật lý trực tiếp; không đoán bottleneck từ tên ───
    ("compat_cpu_gpu_bottleneck",
     "AMD Ryzen 3 3200G đi với GPU MSI VENTUS 2X OC GeForce RTX 5070 12GB GDDR7 có ổn không",
     [("tương thích", "phù hợp", "ổn")]),
]

_cleared_sessions = set()

_TRAILING_ZERO_DECIMAL = re.compile(r'^(\d+)\.(0*)$')


def _token_in_reply(token: str, reply_lower: str) -> bool:
    token = token.strip()
    m = _TRAILING_ZERO_DECIMAL.match(token)
    if m:
        base = m.group(1)
        pattern = rf'\b{re.escape(base)}(?:[.,]\d+)?\b'
        return re.search(pattern, reply_lower) is not None
    return token.lower() in reply_lower


def _check_requirement(requirement, reply_lower: str) -> bool:
    """requirement là chuỗi (phải khớp) hoặc tuple các chuỗi đồng nghĩa
    (chỉ cần 1 trong các lựa chọn khớp)."""
    if isinstance(requirement, (tuple, list)):
        return any(_token_in_reply(alt, reply_lower) for alt in requirement)
    return _token_in_reply(requirement, reply_lower)


def _format_requirement(requirement) -> str:
    if isinstance(requirement, (tuple, list)):
        return " hoặc ".join(requirement)
    return requirement


def _session_id_for(label: str) -> str:
    # Mỗi case compat dùng session riêng — câu hỏi compat thường đứng độc
    # lập (không cần đại từ nối tiếp), nhưng tách session vẫn tránh được
    # rủi ro history của case trước ảnh hưởng đến reformulate ở case sau.
    return f"test_compat_{label}"


def _ensure_clean_session(session_id: str):
    if session_id in _cleared_sessions:
        return
    try:
        client.delete(f"{SESSION_API_BASE}/{session_id}", headers=get_auth_headers())
    except Exception:
        pass
    _cleared_sessions.add(session_id)


def setup_module(module):
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("# BÁO CÁO KIỂM THỬ TƯƠNG THÍCH LINH KIỆN\n\n")
        f.write("| # | Session | Câu hỏi | Trả lời | Yêu cầu | Kết quả |\n")
        f.write("|---|---|---|---|---|---|\n")


def _extract_reply(response_json: dict) -> str:
    if "data" in response_json and isinstance(response_json["data"], dict):
        return response_json["data"].get("chatbot_reply", "Lỗi phản hồi")
    return response_json.get("chatbot_reply", "Lỗi phản hồi")


@pytest.mark.parametrize("label, question, expected_keywords", COMPAT_TEST_CASES)
def test_compatibility(label, question, expected_keywords):
    session_id = _session_id_for(label)
    _ensure_clean_session(session_id)

    payload = {"user_message": question, "session_id": session_id}
    
    passed = False
    missing = []
    reply = ""
    error_msg = ""
    
    try:
        response = client.post(API_URL, json=payload, headers=get_auth_headers())
        if response.status_code not in (200, 201):
            error_msg = f"HTTP {response.status_code}: {response.text}"
            reply = f"❌ LỖI API: {error_msg}"
        else:
            reply = _extract_reply(response.json())
            reply_lower = reply.lower()
            missing = [req for req in expected_keywords if not _check_requirement(req, reply_lower)]
            passed = len(missing) == 0
    except Exception as e:
        error_msg = f"Exception: {str(e)}"
        reply = f"❌ LỖI KẾT NỐI: {error_msg}"

    with open(REPORT_FILE, "a", encoding="utf-8") as f:
        if error_msg:
            result_cell = "❌ Lỗi API"
        else:
            result_cell = "✅" if passed else f"❌ thiếu: {', '.join(_format_requirement(m) for m in missing)}"
            
        keywords_display = ", ".join(_format_requirement(r) for r in expected_keywords)
        reply_clean = reply.replace("\n", "<br>").replace("|", "\\|")
        question_clean = question.replace("\n", "<br>").replace("|", "\\|")
        keywords_clean = keywords_display.replace("\n", "<br>").replace("|", "\\|")
        f.write(
            f"| {label} | {session_id} | {question_clean} | {reply_clean} | "
            f"{keywords_clean} | {result_cell} |\n"
        )

    if error_msg:
        pytest.fail(error_msg)
    else:
        assert passed, f"Thiếu {[_format_requirement(m) for m in missing]} trong câu trả lời: '{reply}'"
