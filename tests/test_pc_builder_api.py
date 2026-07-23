import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from tests.utils import get_auth_headers
import re
import pytest
import requests
import os

API_URL = "http://127.0.0.1:8000/chat"
SESSION_API_BASE = "http://127.0.0.1:8000/sessions"
REPORT_FILE = "tests/reports/report_pc_builder_api.md"

# expected_keywords: mỗi phần tử là 1 "yêu cầu" — TẤT CẢ yêu cầu phải thỏa.
# Một yêu cầu là:
#   - chuỗi: phải xuất hiện đúng (case-insensitive)
#   - tuple các chuỗi: CHỈ CẦN 1 trong các lựa chọn xuất hiện (đồng nghĩa)
TEST_CASES = [
    # ─── [NHÓM 1]: NHẬN DIỆN INTENT & NGÂN SÁCH CƠ BẢN ───
    ("build_budget_basic_1", "build pc 30 triệu chơi game", [("triệu", "tr", "₫"), "game", "- mã bộ:"]),
    ("build_budget_basic_2", "build pc 15 triệu văn phòng", [("triệu", "tr", "₫"), ("văn phòng", "office"), "- mã bộ:"]),
    ("build_budget_basic_3", "lắp pc gaming 50 triệu", ["50", ("gaming", "game"), "- mã bộ:"]),

    # ─── [NHÓM 2]: KIỂM TRA ĐẦY ĐỦ THÀNH PHẦN TRONG BỘ PC ───
    ("build_goi_y_30m", "build pc 30 triệu chơi game aaa", ["- mã bộ:", "cpu", "gpu", "mainboard", "phí lắp ráp", "tổng cộng"]),
    ("build_goi_y_20m", "bộ máy tính văn phòng 20 triệu", ["- mã bộ:", "cpu", "mainboard", "tổng cộng"]),
    ("build_goi_y_80m", "bộ pc deep learning huấn luyện AI 80 triệu", ["- mã bộ:", "cpu", "gpu", "mainboard", ("triệu", "tr", "₫")]),

    # ─── [NHÓM 3]: EDGE CASES — THIẾU NGÂN SÁCH / MỤC ĐÍCH / LỖI GIÁ ───
    ("build_no_budget", "tư vấn bộ pc chơi game", [("ngân sách", "tầm giá", "bao nhiêu tiền", "đầu tư", "chi phí")]),
    ("build_no_purpose", "build pc 30 triệu", ["- mã bộ:"]),
    ("build_too_cheap", "pc 1 triệu chơi game", [("không tìm được", "không có", "chưa có", "khoảng giá", "không phù hợp", "ngân sách", "bao nhiêu tiền", "rất tiếc")]),
    ("build_negative", "build pc âm 30 triệu chơi game", [("không hợp lệ", "nhập lại", "ngân sách", "mâu thuẫn")]),

    # ─── [NHÓM 4]: EDGE CASES — BRAND & COMPONENT FILTER ───
    ("build_intel_filter", "build pc intel 30 triệu chơi game", ["- mã bộ:", "intel"]),
    ("build_nvidia_filter", "build bộ pc nvidia 40 triệu render", ["- mã bộ:", "nvidia"]),
    ("build_amd_filter", "bộ pc amd 25 triệu", ["- mã bộ:"]),
    ("build_rtx4080", "build pc có rtx 4080 tầm 60 triệu", ["- mã bộ:", "rtx 4080"]),
    ("build_gpu_not_found", "build pc có rtx 9090 tầm 30 triệu", [("chưa có", "không tìm được", "chưa có bộ pc nào sử dụng gpu", "rất tiếc")]),
    ("build_upgrade_scenario", "tôi đang có sẵn rtx 4070, hãy build phần còn lại với 15 triệu chơi game", [("- mã bộ:", "ghi nhận", "có sẵn", "rtx 4070")]),
    ("build_combo_review", "Hãy đánh giá bộ PC build sẵn này: AMD Ryzen 7 9800X3D + MSI B850 PRO B850M-VC WIFI6E AM5 DDR5 Micro ATX + MSI GAMING TRIO GeForce RTX 4080 16GB GDDR6X Black. Bộ này phù hợp nhu cầu nào, hiệu năng ra sao, giá trị so với chi phí thế nào và có nên mua không?", ["đánh giá", "9800x3d", "rtx 4080", "b850", "60", ("nên", "phù hợp")]),
    ("build_custom_combo_review", "AMD Ryzen 5 8600G + MSI B850 PRO B850M-VC WIFI6E AM5 DDR5 Micro ATX + MSI GeForce RTX 5070 Ti 16G MLG EDITION OC GDDR7 hãy đánh giá bộ pc này hiệu năng như thế nào", ["8600g", "rtx 5070 ti", "b850", "tương thích", ("điểm nghẽn", "yếu hơn")]),
    ("build_id_combo_review", "BUILD-03909: AMD Ryzen 7 9800X3D + MSI B850 PRO B850M-VC WIFI6E AM5 DDR5 Micro ATX + MSI GAMING TRIO GeForce RTX 4080 16GB GDDR6X Black hãy đánh giá cấu hình này", ["tương thích", ("hợp", "phù hợp", "đánh giá", "tốt", "ngon")]),
    ("build_explicit_id", "cho mình hỏi bộ build-11 có ngon không", ["build-11", ("ngon", "tốt", "mạnh", "phù hợp", "cấu hình", "dạ")]),

    # ─── [NHÓM 5]: EDGE CASES — SỐ LƯỢNG BỘ PC ───
    ("build_qty_10", "mua 10 bộ pc tiệm net 200 triệu", [("10", "10 bộ"), ("tổng", "chi phí", "ngân sách")]),
    ("build_qty_too_low", "mua 3 bộ pc 12 triệu", [("quá thấp", "không đủ", "mỗi bộ chỉ có", "mâu thuẫn")]),

    # ─── [NHÓM 6]: EDGE CASES — "RẺ NHẤT" / "TỐT NHẤT" ───
    ("build_cheapest", "cho mình xem bộ pc rẻ nhất của shop", ["- mã bộ:", "cpu", "gpu", "rẻ nhất"]),
    ("build_best_no_budget", "bộ pc tốt nhất shop có là gì", [("ngân sách", "tầm giá", "bao nhiêu tiền", "đầu tư")]),
]

MULTI_TURN_CASES = [
    # (label, list_of_turns: [(question, expected_keywords), ...])
    (
        "multi_inherit_budget",
        [
            ("tư vấn bộ pc chơi game", [("ngân sách", "tầm giá", "bao nhiêu tiền")]),
            ("tầm 35 triệu", [("nhu cầu", "game cụ thể", "thể loại")]),
            ("chơi Valorant 1080p 240 FPS", ["- mã bộ:", ("giá", "vnđ", "triệu", "₫")]),
        ]
    ),
    (
        "multi_qty_purpose_followup",
        [
            ("mua 3 bộ pc 15 triệu", [("ngân sách", "5", "15")]),
            ("thôi build 1 bộ pc theo nhu cầu chơi game đi", [("nhu cầu", "game cụ thể", "thể loại")]),
            ("chơi Valorant 1080p 144 FPS", [("- mã bộ:", "không tìm được", "không có", "không phù hợp")]),
        ]
    ),
    (
        "multi_adjust_higher",
        [
            ("build pc chơi game 30 triệu", [("nhu cầu", "game cụ thể", "thể loại")]),
            ("chơi Valorant 1080p 240 FPS", ["- mã bộ:", "30"]),
            ("cho mình xem bộ đắt hơn", ["- mã bộ:", ("triệu", "tr", "₫")]),
        ]
    ),
    (
        "multi_adjust_lower",
        [
            ("build pc chơi game 30 triệu", [("nhu cầu", "game cụ thể", "thể loại")]),
            ("chơi Valorant 1080p 240 FPS", ["- mã bộ:", "30"]),
            ("bộ rẻ hơn chút được không", [("rẻ hơn", "thấp hơn", "tham khảo", "asus", "- mã bộ:")]),
        ]
    ),
    (
        "multi_inherit_component_basic",
        [
            ("CPU i5 13600K có mạnh không?", [("mạnh", "i5", "13600k", "có")]),
            ("build cho tôi bộ 30 triệu chơi Valorant 1080p 240 FPS", ["- mã bộ:", ("i5-13600k", "13600k")]),
        ]
    ),
    (
        "multi_inherit_component_change_mind",
        [
            ("rtx 3060 ti chơi pubg mượt không?", [("mượt", "rtx", "3060 ti", "chưa tìm thấy", "không tìm thấy")]),
            ("vậy rtx 4070 thì sao?", [("4070", "rtx", "hơn", "chưa tìm thấy", "không tìm thấy", "kho")]),
            ("build cho tôi bộ 50 triệu chơi PUBG 2K 144 FPS đi", ["- mã bộ:", "4070"]),
        ]
    ),
    (
        "multi_reset_intent",
        [
            ("build pc có rtx 3060 ti tầm 30 triệu để chơi PUBG 1080p 144 FPS", ["- mã bộ:", "3060 ti"]),
            ("thôi build cho tôi bộ mới hoàn toàn tầm 60 triệu đi", [("làm gì", "mục đích", "nhu cầu")]),
            ("để chơi game AAA 4K ray tracing", ["- mã bộ:", "60"]),
        ]
    ),
    (
        "multi_question_current_build",
        [
            ("build pc 30 triệu chơi GTA 5 1080p 144 FPS", ["- mã bộ:", "30"]),
            ("cấu hình này chơi mượt gta 5 không shop?", [("mượt", "chơi được", "tốt", "thoải mái", "chiến", "khá", "ổn")]),
        ]
    ),
]

_cleared_sessions = set()
_test_results = []

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
    response = requests.delete(
        f"{SESSION_API_BASE}/{session_id}", timeout=10, headers=get_auth_headers()
    )
    response.raise_for_status()
    _cleared_sessions.add(session_id)


def _update_md_report():
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    total = len(_test_results)
    passed = sum(1 for r in _test_results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    md_content = f"""# 🚀 Báo Cáo Kiểm Thử Tích Hợp API - PC Builder

Kiểm thử tự động phản hồi của LLM Vi-Qwen 1.5B qua API HTTP POST `/chat`.

## 📊 Thống kê chung
- **Tổng số Test Cases:** {total}
- **Thành công (PASS):** {passed}
- **Thất bại (FAIL):** {failed}
- **Tỷ lệ thành công:** {pass_rate:.1f}%

## 📋 Chi tiết kết quả kiểm thử

| # | Nhóm / Label | Session ID | Câu hỏi (Input) | Phản hồi từ Bot (LLM Reply) | Từ khóa mong đợi | Kết quả |
|---|---|---|---|---|---|---|
"""
    for idx, r in enumerate(_test_results, 1):
        status = "✅ PASS" if r["passed"] else f"❌ FAIL<br>Thiếu: `{r['missing']}`"
        reply_clean = r["reply"].replace("\n", "<br>").replace("|", "\\|")
        question_clean = r["question"].replace("\n", "<br>").replace("|", "\\|")
        expected_clean = r["expected"].replace("\n", "<br>").replace("|", "\\|")
        md_content += f"| {idx} | `{r['label']}` | `{r['session_id']}` | {question_clean} | {reply_clean} | `{expected_clean}` | {status} |\n"

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(md_content)


def setup_module(module):
    _test_results.clear()
    _update_md_report()


def _extract_reply(response_json: dict) -> str:
    if "data" in response_json and isinstance(response_json["data"], dict):
        return response_json["data"].get("chatbot_reply", "Lỗi phản hồi")
    return response_json.get("chatbot_reply", "Lỗi phản hồi")


@pytest.mark.parametrize("label, question, expected_keywords", TEST_CASES)
def test_single_turn(label, question, expected_keywords):
    session_id = _session_id_for(label)
    _ensure_clean_session(session_id)

    error_msg = ""
    try:
        response = requests.post(
            API_URL,
            json={"user_message": question, "session_id": session_id},
            timeout=90,
            headers=get_auth_headers(),
        )
        response.raise_for_status()
        reply = _extract_reply(response.json())
    except Exception as error:
        error_msg = str(error)
        reply = f"❌ LỖI KẾT NỐI: {error_msg}"

    reply_lower = reply.lower()
    missing = [req for req in expected_keywords if not _check_requirement(req, reply_lower)]
    passed = not error_msg and not missing

    keywords_display = ", ".join(_format_requirement(r) for r in expected_keywords)
    missing_display = "Lỗi API" if error_msg else ", ".join(_format_requirement(m) for m in missing)

    _test_results.append({
        "label": label,
        "session_id": session_id,
        "question": question,
        "reply": reply,
        "expected": keywords_display,
        "passed": passed if not error_msg else False,
        "missing": missing_display
    })
    _update_md_report()

    if error_msg:
        pytest.fail(error_msg)
    else:
        if label == "build_combo_review":
            assert "850 triệu" not in reply_lower, f"Không được hiểu B850 là ngân sách: '{reply}'"
        assert passed, f"Thiếu {[_format_requirement(m) for m in missing]} trong câu trả lời: '{reply}'"


@pytest.mark.parametrize("label, turns", MULTI_TURN_CASES)
def test_multi_turn(label, turns):
    session_id = _session_id_for(label)
    _ensure_clean_session(session_id)

    for turn_idx, (question, expected_keywords) in enumerate(turns, 1):
        error_msg = ""
        try:
            response = requests.post(
                API_URL,
                json={"user_message": question, "session_id": session_id},
                timeout=90,
                headers=get_auth_headers(),
            )
            response.raise_for_status()
            reply = _extract_reply(response.json())
        except Exception as error:
            error_msg = str(error)
            reply = f"❌ LỖI KẾT NỐI: {error_msg}"

        reply_lower = reply.lower()
        missing = [req for req in expected_keywords if not _check_requirement(req, reply_lower)]
        passed = not error_msg and not missing

        keywords_display = ", ".join(_format_requirement(r) for r in expected_keywords)
        missing_display = "Lỗi API" if error_msg else ", ".join(_format_requirement(m) for m in missing)

        _test_results.append({
            "label": f"{label} [Turn {turn_idx}]",
            "session_id": session_id,
            "question": question,
            "reply": reply,
            "expected": keywords_display,
            "passed": passed if not error_msg else False,
            "missing": missing_display
        })
        _update_md_report()

        if error_msg:
            pytest.fail(f"Lỗi ở turn '{question}': {error_msg}")
        else:
            assert passed, f"Thiếu {[_format_requirement(m) for m in missing]} trong câu trả lời: '{reply}'"
