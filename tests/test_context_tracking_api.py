import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from utils import get_auth_headers
import pytest
import requests
import re

API_URL = "http://127.0.0.1:8000/chat"
SESSION_API_BASE = "http://127.0.0.1:8000/sessions"
REPORT_FILE = "tests/reports/report_context_tracking_api.md"

MULTI_TURN_CASES = [
    (
        "multi_inherit_price",
        [
            ("rtx 5070 ti giá bao nhiêu?", ["19.919.760"]),
            ("vậy rtx 5080 thì sao?", ["37.559.760"]),
            ("thế còn ryzen 5 7600x?", ["4.091.760"]),
        ]
    ),
    (
        "multi_inherit_spec",
        [
            ("rtx 5070 ti vram bao nhiêu?", ["16", ("vram", "gb")]),
            ("thế còn xung nhịp?", [("2295", "2467", "2572", "2.295", "2.467", "2.572"), ("mhz", "ghz", "xung", "nhịp")]),
            ("vậy của rtx 5080 thì sao?", ["5080", ("2205", "2295", "2610", "2625", "2640", "2.205", "2.295", "2.610", "2.625", "2.640"), ("mhz", "ghz", "xung", "nhịp")]),
        ]
    ),
    (
        "multi_inherit_compat",
        [
            ("ryzen 5 7600x có lắp được với main MSI PRO B650M-P không?", [("tương thích", "lắp được", "phù hợp")]),
            ("thế còn main ASUS B760M-AYW thì sao?", ["b760m-ayw", ("không", "không tương thích")]),
            ("vậy đi với i7 14700k?", ["14700k", ("tương thích", "lắp được", "phù hợp")]),
        ]
    ),
    (
        "multi_inherit_general",
        [
            ("tìm cho mình card đồ họa nvidia", [("nvidia", "rtx", "gtx")]),
            ("có loại nào tầm 10 triệu không?", [("11.995.920", "11.976.000", "vnđ")]),
        ]
    ),
    (
        "multi_inherit_build_pc",
        [
            ("rtx 3080 chơi pubg mượt không?", ["3080", ("mượt", "tốt", "ổn", "có")]),
            ("vậy rtx 4080 thì sao?", ["4080", ("pubg", "mượt", "tốt", "ổn", "hiệu suất")]),
            ("build cho tôi bộ 50 triệu chơi game đi", ["- mã bộ:", ("4080", "3080", "3080ti", "3080 ti"), "triệu"]),
        ]
    ),
    (
        "multi_non_exists_general",
        [
            ("tìm cho mình ssd samsung", [("chưa tìm thấy", "không tìm thấy", "không có")]),
            ("có loại 1TB không?", [("chưa tìm thấy", "không tìm thấy", "không có")]),
        ]
    ),
]

_cleared_sessions = set()
_test_results = []
_TRAILING_ZERO_DECIMAL = re.compile(r'^(\d+)\.(0*)$')

def _session_id_for(label: str) -> str:
    return f"test_context_{label}"

def _ensure_clean_session(session_id: str):
    if session_id in _cleared_sessions:
        return
    try:
        requests.delete(f"{SESSION_API_BASE}/{session_id}", timeout=10, headers=get_auth_headers())
    except requests.RequestException:
        pass
    _cleared_sessions.add(session_id)

def _update_md_report():
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    total = len(_test_results)
    passed = sum(1 for r in _test_results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    md_content = f"""# 🚀 Báo Cáo Kiểm Thử Tích Hợp API - Context Tracking

Kiểm thử khả năng duy trì ngữ cảnh (intent, products, category) qua API HTTP POST `/chat`.

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

@pytest.mark.parametrize("label, turns", MULTI_TURN_CASES)
def test_multi_turn_context(label, turns):
    session_id = _session_id_for(label)
    _ensure_clean_session(session_id)
    failed_turns = []

    for turn_idx, (question, expected_keywords) in enumerate(turns, 1):
        print(f"\n▶ Đang chạy [Turn {turn_idx}]: {question}...")
        payload = {"user_message": question, "session_id": session_id}
        
        passed = False
        missing = []
        reply = ""
        error_msg = ""
        
        try:
            response = requests.post(API_URL, json=payload, timeout=90, headers=get_auth_headers())
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
            failed_turns.append(f"Lỗi ở turn {turn_idx} '{question}': {error_msg}")
        elif not passed:
            failed_turns.append(f"Turn {turn_idx} thiếu {[_format_requirement(m) for m in missing]} trong câu trả lời: '{reply}'")

    if failed_turns:
        pytest.fail("\n".join(failed_turns))
