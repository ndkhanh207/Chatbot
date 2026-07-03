import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from utils import get_auth_headers
import re
import pytest
import requests
import os

API_URL = "http://127.0.0.1:8000/chat"
SESSION_API_BASE = "http://127.0.0.1:8000/sessions"
REPORT_FILE = "tests/reports/report_specification.md"

# expected_keywords: mỗi phần tử là 1 "yêu cầu" — TẤT CẢ yêu cầu phải thỏa.
# Một yêu cầu là:
#   - chuỗi: phải xuất hiện đúng (case-insensitive)
#   - tuple các chuỗi: CHỈ CẦN 1 trong các lựa chọn xuất hiện (đồng nghĩa)
# Số dạng "X." hoặc "X.0"/"X.00" được tự match linh hoạt với cả "X" trơn
# hoặc "X.bất kỳ số nào" trong câu trả lời — không ảnh hưởng số thập phân
# thật (như "4.5" GHz vẫn phải khớp chính xác, không bị nới).
TEST_CASES = [
    # ─── [CPU 1]: INTEL CORE I9 14900K ───
    ("cpu_i9_14900k", "tên đầy đủ của con chip i9 14900K là gì", ["i9-14900k", "intel"]),
    ("cpu_i9_14900k", "giá của i9 14900K là bao nhiêu", ["vnđ", "giá"]),
    ("cpu_i9_14900k", "i9 14900K có bao nhiêu lõi", ["lõi", "core"]),
    ("cpu_i9_14900k", "xung cơ bản của i9 14900K là mấy", ["ghz", "cơ bản"]),
    ("cpu_i9_14900k", "xung boost của i9 14900K là bao nhiêu", ["ghz", "boost"]),
    ("cpu_i9_14900k", "kiến trúc của i9 14900K là gì", ["kiến trúc"]),
    ("cpu_i9_14900k", "tdp của i9 14900K là bao nhiêu watt", ["w", "tdp"]),
    ("cpu_i9_14900k", "i9 14900K có đồ họa tích hợp không", [("đồ họa", "gpu")]),
    ("cpu_i9_14900k", "socket của i9 14900K là gì", ["LGA 1700", "socket"]),

    # ─── [CPU 2]: AMD RYZEN 7 7700X ───
    ("cpu_ryzen_7700x", "tên đầy đủ của chip Ryzen 7 7700X là gì vậy", ["ryzen", "7700x"]),
    ("cpu_ryzen_7700x", "giá con chip AMD Ryzen 7 7700X bao nhiêu", ["5.831.520", "vnđ"]),
    ("cpu_ryzen_7700x", "Ryzen 7 7700X có mấy lõi", ["8", "lõi"]),
    ("cpu_ryzen_7700x", "xung cơ bản của ryzen 7 7700X là bao nhiêu", ["4.5", "ghz"]),
    ("cpu_ryzen_7700x", "xung boost của chip ryzen 7 7700x là bao nhiêu", ["5.4", "ghz"]),
    ("cpu_ryzen_7700x", "kiến trúc của ryzen 7 7700x là gì", ["zen 4"]),
    ("cpu_ryzen_7700x", "tdp của ryzen 7 7700x tiêu thụ bao nhiêu", ["105", "w"]),
    ("cpu_ryzen_7700x", "đồ họa tích hợp của 7700x tên là gì", ["radeon"]),
    ("cpu_ryzen_7700x", "ryzen 7 7700x dùng socket nào vậy shop", ["am5", "socket"]),

    # ─── [GPU 1]: MSI GeForce RTX 5070 Ti 16G MLG EDITION OC GDDR7 ───
    ("gpu_msi_mlg", "Cho mình xin tên đầy đủ của card MSI 5070 Ti MLG với", ["msi", "geforce", "rtx", "5070", "ti", "mlg"]),
    ("gpu_msi_mlg", "Con card MSI RTX 5070 Ti MLG EDITION này hiện tại bao nhiêu tiền", ["19.919.760", "vnđ"]),
    ("gpu_msi_mlg", "Card MSI MLG 5070 Ti này chạy chipset gì vậy", ["geforce", "rtx", "5070", "ti"]),
    ("gpu_msi_mlg", "Dung lượng VRAM của con MSI 5070 Ti MLG này là bao nhiêu", ["16.0", "gb"]),
    ("gpu_msi_mlg", "Cho mình biết xung cơ bản của con MSI RTX 5070 Ti MLG này là mấy", ["2295.0", "mhz"]),
    ("gpu_msi_mlg", "Xung boost của card MSI 5070 Ti MLG EDITION này lên được tối đa bao nhiêu", ["2572.0", "mhz"]),
    ("gpu_msi_mlg", "Card MSI RTX 5070 Ti MLG EDITION OC này thiết kế màu gì thế shop", ["màu đỏ"]),
    ("gpu_msi_mlg", "Chiều dài của con card MSI 5070 Ti MLG này là bao nhiêu mm", ["338.0", "mm"]),
    # ⚠ Bot từng trả 285W (dataset thật = 300W) — GIỮ keyword nghiêm ngặt,
    # KHÔNG thêm "285" làm alternative, để test tiếp tục bắt lỗi hallucination này.
    ("gpu_msi_mlg", "Điện năng tiêu thụ TDP của con MSI 5070 Ti MLG OC này là bao nhiêu watt", ["300.0", "w"]),
    ("gpu_msi_mlg", "Card đồ họa MSI RTX 5070 Ti MLG dùng chuẩn giao tiếp gì", ["pcie", "5.0", "x16"]),

    # ─── [GPU 2]: GIGABYTE GeForce RTX 5070 Ti GAMING 16G ───
    ("gpu_giga_gaming", "Shop đọc giúp mình tên chính xác của card Gigabyte 5070 Ti bản Gaming", ["gigabyte", "geforce", "rtx", "5070", "ti"]),
    ("gpu_giga_gaming", "Con card GIGABYTE RTX 5070 Ti GAMING 16G giá bao nhiêu shop", ["19.919.760", "vnđ"]),
    ("gpu_giga_gaming", "Chipset xử lý của con Gigabyte 5070 Ti Gaming này là loại nào", ["geforce", "rtx", "5070", "ti"]),
    ("gpu_giga_gaming", "Con card Gigabyte 5070 Ti Gaming này bộ nhớ bao nhiêu GB", ["16.0", "gb"]),
    # ⚠ Bot từng trả lời nhầm sang "Gigabyte X570S GAMING X AM4" (mainboard,
    # không phải GPU) — GIỮ nghiêm ngặt để test tiếp tục bắt lỗi search sai sản phẩm.
    ("gpu_giga_gaming", "Xung cơ bản mặc định của Gigabyte 5070 Ti Gaming 16G là bao nhiêu MHz", ["2295.0", "mhz"]),
    ("gpu_giga_gaming", "Xung boost của bản Gigabyte 5070 Ti Gaming 16G này chạy lên được bao nhiêu", ["2588.0", "mhz"]),
    ("gpu_giga_gaming", "Mẫu card Gigabyte RTX 5070 Ti Gaming này có hệ thống màu sắc led gì không", ["rgb"]),
    ("gpu_giga_gaming", "Chiều dài của con card Gigabyte RTX 5070 Ti Gaming này dài bao nhiêu thế shop", ["342.0", "mm"]),
    ("gpu_giga_gaming", "Công suất tiêu thụ TDP của card Gigabyte 5070 Ti Gaming này ăn bao nhiêu watt", ["300.0", "w"]),
    ("gpu_giga_gaming", "Giao tiếp khe cắm của con card Gigabyte 5070 Ti Gaming 16G này là chuẩn gì", ["pcie", "5.0", "x16"]),

    # ─── [MAINBOARD 1]: ASUS B760M-AYW WIFI D4 ───
    ("main_asus_b760m", "Mainboard Asus B760M bản chạy ram d4 có wifi tên chính xác là gì nhỉ", ["asus", "b760m-ayw", "wifi", "d4"]),
    ("main_asus_b760m", "Bo mạch chủ ASUS B760M-AYW WIFI D4 giá bao nhiêu vậy shop", ["4.858.808", "vnđ"]),
    ("main_asus_b760m", "Cho mình hỏi main ASUS B760M-AYW WIFI D4 dùng socket nào", ["lga", "1700"]),
    ("main_asus_b760m", "Kích thước Form factor của con main Asus B760M AYW Wifi này là chuẩn gì", ["micro", "atx"]),
    ("main_asus_b760m", "Bo mạch chủ ASUS B760M-AYW WIFI D4 nhận được tối đa bao nhiêu GB RAM", ["64", "gb"]),
    ("main_asus_b760m", "Trên con main Asus B760M-AYW này thiết kế mấy khe cắm RAM", ["2", "khe"]),
    ("main_asus_b760m", "Ngoại hình của con mainboard Asus B760M-AYW WIFI D4 này phối màu như thế nào", ["xám", "đen"]),
    ("main_asus_b760m", "Con main Asus B760M AYW Wifi này dùng RAM DDR4 hay DDR5 thế", ["ddr4"]),
    # ⚠ Bot từng trả "không tìm thấy mã sản phẩm" (search rỗng hoàn toàn cho
    # câu hỏi chứa "M.2") — GIỮ nghiêm ngặt để test tiếp tục bắt lỗi này.
    ("main_asus_b760m", "Khe cắm SSD M.2 trên con main Asus B760M-AYW này chạy ở băng thông chuẩn nào", ["pcie", "4.0", "x4"]),
    ("main_asus_b760m", "Chuẩn kết nối ổ cứng lưu trữ SATA của mainboard Asus B760M-AYW WIFI D4 là gì", ["sata_6_gb_s"]),
    ("main_asus_b760m", "Khe cắm card đồ họa mở rộng PCIe chính trên main Asus B760M-AYW chạy chuẩn gì", ["pcie", "4.0", "x16"]),

    # ─── [MAINBOARD 2]: MSI B850 PRO B850M-VC WIFI6E AM5 DDR5 Micro ATX ───
    ("main_msi_b850", "Đọc giúp mình tên đầy đủ của con main MSI dòng B850 socket AM5 kích thước nhỏ với", ["msi", "b850", "pro", "b850m-vc"]),
    ("main_msi_b850", "Con mainboard MSI B850 PRO B850M-VC này giá bán hiện tại là bao nhiêu", ["4.992.114", "vnđ"]),
    ("main_msi_b850", "Cho hỏi main MSI B850 PRO này dùng socket gì để chọn CPU lắp cùng", ["am5"]),
    ("main_msi_b850", "Kích cỡ bo mạch của con main MSI B850 PRO B850M-VC này lớn hay nhỏ chuẩn gì", ["micro", "atx"]),
    ("main_msi_b850", "Main MSI B850 PRO B850M-VC cắm được tối đa bao nhiêu dung lượng RAM hệ thống", ["256", "gb"]),
    ("main_msi_b850", "Mainboard MSI B850 PRO B850M-VC AM5 có mấy khe để cắm thanh RAM", ["4", "khe"]),
    ("main_msi_b850", "Bo mạch chủ MSI B850 PRO B850M-VC này có màu gì vậy shop", ["đen"]),
    ("main_msi_b850", "Con main MSI dòng B850 PRO này bắt buộc chạy RAM thế hệ nào", ["ddr5"]),
    ("main_msi_b850", "Giao tiếp ổ cứng SSD M.2 trên main MSI B850M-VC này chạy tốc độ nào", ["pcie", "4.0", "x4"]),
    ("main_msi_b850", "Thông số cổng lưu trữ mở rộng SATA của main MSI B850 PRO này như thế nào", [("không có", "chưa có", "chưa được cập nhật")]),
    ("main_msi_b850", "Khe cắm PCIe chính mở rộng trên chiếc mainboard MSI B850 PRO AM5 này chạy băng thông bao nhiêu", ["pcie", "4.0", "x16"]),
]

_cleared_sessions = set()

# Số dạng "X." hoặc "X.0"/"X.00..." (toàn số 0 sau dấu chấm, hoặc không có
# gì sau dấu chấm) được coi là "số nguyên viết kèm .0 dư" — match linh hoạt
# với "X" trơn hoặc "X.<bất kỳ chữ số nào>" trong câu trả lời.
# KHÔNG áp dụng cho số có phần thập phân thật (vd "4.5", "5.4") — những số
# đó vẫn phải khớp CHÍNH XÁC, và KHÔNG áp dụng cho số có nhiều dấu chấm
# kiểu phân tách nghìn (vd "19.919.760", "4.858.808") — giá tiền vẫn phải
# khớp đúng từng ký tự.
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
    return f"test_{label}"


def _ensure_clean_session(session_id: str):
    if session_id in _cleared_sessions:
        return
    try:
        requests.delete(f"{SESSION_API_BASE}/{session_id}", timeout=10, headers=get_auth_headers())
    except requests.RequestException:
        pass
    _cleared_sessions.add(session_id)


def setup_module(module):
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("# BÁO CÁO KIỂM THỬ CHATBOT\n\n")
        f.write("| # | Session | Câu hỏi | Trả lời | Từ khóa cần có | Kết quả |\n")
        f.write("|---|---|---|---|---|---|\n")


def _extract_reply(response_json: dict) -> str:
    if "data" in response_json and isinstance(response_json["data"], dict):
        return response_json["data"].get("chatbot_reply", "Lỗi phản hồi")
    return response_json.get("chatbot_reply", "Lỗi phản hồi")


@pytest.mark.parametrize("label, question, expected_keywords", TEST_CASES)
def test_export_qa(label, question, expected_keywords):
    session_id = _session_id_for(label)
    _ensure_clean_session(session_id)

    payload = {"user_message": question, "session_id": session_id}
    response = requests.post(API_URL, json=payload, timeout=30, headers=get_auth_headers())

    assert response.status_code in (200, 201), (
        f"HTTP {response.status_code} cho câu hỏi '{question}': {response.text}"
    )

    reply = _extract_reply(response.json())
    reply_lower = reply.lower()
    missing = [req for req in expected_keywords if not _check_requirement(req, reply_lower)]
    passed = len(missing) == 0

    with open(REPORT_FILE, "a", encoding="utf-8") as f:
        result_cell = "✅" if passed else f"❌ thiếu: {', '.join(_format_requirement(m) for m in missing)}"
        keywords_display = ", ".join(_format_requirement(r) for r in expected_keywords)
        reply_clean = reply.replace("\n", "<br>").replace("|", "\\|")
        question_clean = question.replace("\n", "<br>").replace("|", "\\|")
        keywords_clean = keywords_display.replace("\n", "<br>").replace("|", "\\|")
        f.write(
            f"| {label} | {session_id} | {question_clean} | {reply_clean} | "
            f"{keywords_clean} | {result_cell} |\n"
        )

    assert passed, f"Thiếu {[_format_requirement(m) for m in missing]} trong câu trả lời: '{reply}'"