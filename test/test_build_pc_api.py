import re
import pytest
import requests
import os

API_URL = "http://127.0.0.1:8000/chat"
SESSION_API_BASE = "http://127.0.0.1:8000/sessions"
REPORT_FILE = "test/report_build_api_test.md"

# expected_keywords: mỗi phần tử là 1 "yêu cầu" — TẤT CẢ yêu cầu phải thỏa.
# Một yêu cầu là:
#   - chuỗi: phải xuất hiện đúng (case-insensitive)
#   - tuple các chuỗi: CHỈ CẦN 1 trong các lựa chọn xuất hiện (đồng nghĩa)
TEST_CASES = [
    # ─── [NHÓM 1]: NHẬN DIỆN INTENT & NGÂN SÁCH CƠ BẢN ───
    ("build_budget_basic_1", "build pc 30 triệu chơi game", ["30", ("triệu", "tr"), "game", "[GỢI Ý BỘ PC TỐI ƯU]"]),
    ("build_budget_basic_2", "build pc 15 triệu văn phòng", ["15", ("triệu", "tr"), ("văn phòng", "office"), "[GỢI Ý BỘ PC TỐI ƯU]"]),
    ("build_budget_basic_3", "lắp pc gaming 50 triệu", ["50", ("gaming", "game"), "[GỢI Ý BỘ PC TỐI ƯU]"]),

    # ─── [NHÓM 2]: KIỂM TRA ĐẦY ĐỦ THÀNH PHẦN TRONG BỘ PC ───
    ("build_goi_y_30m", "build pc 30 triệu chơi game aaa", ["[GỢI Ý BỘ PC TỐI ƯU]", "CPU:", "GPU:", "Mainboard:", "Phí lắp ráp:", "Tổng cộng"]),
    ("build_goi_y_20m", "bộ máy tính văn phòng 20 triệu", ["[GỢI Ý BỘ PC TỐI ƯU]", "CPU:", "GPU:", "Mainboard:", "Tổng cộng"]),
    ("build_goi_y_80m", "pc deep learning huấn luyện AI 80 triệu", ["[GỢI Ý BỘ PC TỐI ƯU]", "CPU:", "GPU:", "Mainboard:", "80"]),

    # ─── [NHÓM 3]: EDGE CASES — THIẾU NGÂN SÁCH / MỤC ĐÍCH / LỖI GIÁ ───
    ("build_no_budget", "tư vấn bộ pc chơi game", [("ngân sách", "tầm giá", "bao nhiêu tiền", "đầu tư")]),
    ("build_no_purpose", "build pc 30 triệu", [("làm gì", "mục đích", "nhu cầu", "chủ yếu")]),
    ("build_too_cheap", "pc 1 triệu chơi game", [("không tìm được", "không có", "không phù hợp", "ngân sách")]),
    ("build_negative", "build pc âm 30 triệu chơi game", [("không hợp lệ", "nhập lại", "ngân sách")]),

    # ─── [NHÓM 4]: EDGE CASES — BRAND & COMPONENT FILTER ───
    ("build_intel_filter", "build pc intel 30 triệu chơi game", ["[GỢI Ý BỘ PC TỐI ƯU]", "intel"]),
    ("build_nvidia_filter", "pc nvidia 40 triệu render", ["[GỢI Ý BỘ PC TỐI ƯU]", ("nvidia", "rtx", "gtx")]),
    ("build_amd_filter", "bộ pc amd 25 triệu", ["[GỢI Ý BỘ PC TỐI ƯU]", ("amd", "ryzen", "radeon")]),
    ("build_rtx4080", "build pc có rtx 4080 tầm 60 triệu", ["[GỢI Ý BỘ PC TỐI ƯU]", "rtx 4080"]),
    ("build_gpu_not_found", "build pc có rtx 9090 tầm 30 triệu", [("chưa có", "không tìm được", "chưa có bộ pc nào sử dụng gpu")]),

    # ─── [NHÓM 5]: EDGE CASES — SỐ LƯỢNG BỘ PC ───
    ("build_qty_10", "mua 10 bộ pc tiệm net 200 triệu", ["[GỢI Ý BỘ PC TỐI ƯU]", ("10 bộ", "×10 bộ"), "200", "20"]),
    ("build_qty_too_low", "mua 3 bộ pc 15 triệu", [("quá thấp", "không đủ", "mỗi bộ chỉ có")]),

    # ─── [NHÓM 6]: EDGE CASES — "RẺ NHẤT" / "TỐT NHẤT" ───
    ("build_cheapest", "cho mình xem bộ pc rẻ nhất của shop", ["[GỢI Ý BỘ PC TỐI ƯU]", "CPU:", "GPU:", "rẻ nhất"]),
    ("build_best_no_budget", "bộ pc tốt nhất shop có là gì", [("ngân sách", "tầm giá", "bao nhiêu tiền", "đầu tư")]),
]

MULTI_TURN_CASES = [
    # (label, list_of_turns: [(question, expected_keywords), ...])
    (
        "multi_inherit_budget",
        [
            ("tư vấn bộ pc chơi game", [("ngân sách", "tầm giá", "bao nhiêu tiền")]),
            ("tầm 35 triệu", ["[GỢI Ý BỘ PC TỐI ƯU]", "35", "game"]),
        ]
    ),
    (
        "multi_adjust_higher",
        [
            ("build pc chơi game 30 triệu", ["[GỢI Ý BỘ PC TỐI ƯU]", "30"]),
            ("cho mình xem bộ đắt hơn", ["[GỢI Ý BỘ PC TỐI ƯU]", "game"]),
        ]
    ),
    (
        "multi_adjust_lower",
        [
            ("build pc chơi game 30 triệu", ["[GỢI Ý BỘ PC TỐI ƯU]", "30"]),
            ("bộ rẻ hơn chút được không", ["[GỢI Ý BỘ PC TỐI ƯU]", "game"]),
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
    try:
        requests.delete(f"{SESSION_API_BASE}/{session_id}", timeout=10)
    except requests.RequestException:
        pass
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

    payload = {"user_message": question, "session_id": session_id}
    response = requests.post(API_URL, json=payload, timeout=90)

    assert response.status_code == 200, (
        f"HTTP {response.status_code} cho câu hỏi '{question}': {response.text}"
    )

    reply = _extract_reply(response.json())
    reply_lower = reply.lower()
    missing = [req for req in expected_keywords if not _check_requirement(req, reply_lower)]
    passed = len(missing) == 0

    keywords_display = ", ".join(_format_requirement(r) for r in expected_keywords)
    missing_display = ", ".join(_format_requirement(m) for m in missing)

    _test_results.append({
        "label": label,
        "session_id": session_id,
        "question": question,
        "reply": reply,
        "expected": keywords_display,
        "passed": passed,
        "missing": missing_display
    })
    _update_md_report()

    assert passed, f"Thiếu {[_format_requirement(m) for m in missing]} trong câu trả lời: '{reply}'"


@pytest.mark.parametrize("label, turns", MULTI_TURN_CASES)
def test_multi_turn(label, turns):
    session_id = _session_id_for(label)
    _ensure_clean_session(session_id)

    for turn_idx, (question, expected_keywords) in enumerate(turns, 1):
        payload = {"user_message": question, "session_id": session_id}
        response = requests.post(API_URL, json=payload, timeout=90)

        assert response.status_code == 200, (
            f"HTTP {response.status_code} cho câu hỏi '{question}': {response.text}"
        )

        reply = _extract_reply(response.json())
        reply_lower = reply.lower()
        missing = [req for req in expected_keywords if not _check_requirement(req, reply_lower)]
        passed = len(missing) == 0

        keywords_display = ", ".join(_format_requirement(r) for r in expected_keywords)
        missing_display = ", ".join(_format_requirement(m) for m in missing)

        _test_results.append({
            "label": f"{label} [Turn {turn_idx}]",
            "session_id": session_id,
            "question": question,
            "reply": reply,
            "expected": keywords_display,
            "passed": passed,
            "missing": missing_display
        })
        _update_md_report()

        assert passed, f"[Turn {turn_idx}] Thiếu {[_format_requirement(m) for m in missing]} trong câu trả lời: '{reply}'"
