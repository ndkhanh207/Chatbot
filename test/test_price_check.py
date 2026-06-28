import re
import pytest
import requests
import os

API_URL = "http://127.0.0.1:8000/chat"
SESSION_API_BASE = "http://127.0.0.1:8000/sessions"
REPORT_FILE = "test/reports/report_price_check.md"

TEST_CASES = [
    # ─── [NHÓM 1]: KIỂM TRA GIÁ 1 LINH KIỆN CỤ THỂ (price_check) ───
    ("price_check_rtx4080", "RTX 4080 Super giá bao nhiêu", ["vnđ", ("giá", "khoảng"), "rtx 4080 super"]),
    ("price_check_cpu", "cho mình xin giá i9 14900k", ["vnđ", ("giá", "khoảng"), ("10.536.000", "10 triệu", "10,5", "10.536")]),
    ("price_check_mainboard", "main msi b850 pro giá sao shop", ["vnđ", ("giá", "khoảng"), "msi b850 pro"]),

    # ─── [NHÓM 2]: TÍNH TỔNG GIÁ NHIỀU LINH KIỆN (price_calculation) ───
    ("price_calc_multiple", "i5 12400f với main h610m tổng bao nhiêu tiền", ["tổng", "vnđ", ("i5 12400f", "i5-12400f", "i5"), "h610m"]),

    # ─── [NHÓM 3]: TÌM KIẾM LINH KIỆN THEO NGÂN SÁCH (budget_search) ───
    ("price_budget_search", "tư vấn em con card đồ họa tầm 8 triệu", ["vnđ", ("lọc", "dưới", "khoảng"), ("rtx", "gtx", "rx", "vga", "card")]),
    ("price_top_cheapest", "top 5 CPU giá rẻ nhất dưới 5 triệu", ["vnđ", ("rẻ", "thấp"), "core", "ryzen"]),
    ("price_top_expensive", "top 3 card đồ họa đắt nhất từ 10 đến 20 triệu", ["vnđ", ("đắt", "cao"), ("rtx", "rx")]),
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
    if isinstance(requirement, (tuple, list)):
        return any(_token_in_reply(alt, reply_lower) for alt in requirement)
    return _token_in_reply(requirement, reply_lower)


def _format_requirement(requirement) -> str:
    if isinstance(requirement, (tuple, list)):
        return " hoặc ".join(requirement)
    return requirement


def _session_id_for(label: str) -> str:
    return f"test_price_{label}"


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

    md_content = f"""# 🚀 Báo Cáo Kiểm Thử Tích Hợp API - Price Check & Calculation

Kiểm thử tự động phản hồi của LLM Vi-Qwen 1.5B qua API HTTP POST `/chat` cho các luồng giá.

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
def test_price_flows(label, question, expected_keywords):
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
