import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from tests.utils import get_auth_headers
import pytest
import requests
import re

API_URL = "http://127.0.0.1:8000/chat"
SESSION_API_BASE = "http://127.0.0.1:8000/sessions"
REPORT_FILE = "tests/reports/report_pc_builder_multi_turn_api.md"

MULTI_TURN_CASES = [
    (
        "conversation_budget",
        [
            ("build pc 30 triệu chơi game", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("tăng ngân sách lên 35 triệu", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("thôi chỉ còn 20 triệu", [("cao hơn ngân sách", "tăng ngân sách", "cpu", "mâu thuẫn", "?")]),
        ]
    ),
    (
        "conversation_cpu_lock",
        [
            ("build pc 30 triệu làm văn phòng", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("giữ nguyên cpu nhưng đổi sang rtx 4080", [("cao hơn ngân sách", "tăng ngân sách", "cpu", "mâu thuẫn", "?")]),
            ("ok 50 triệu đi", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("giữ nguyên gpu nhưng đổi sang main z790", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
        ]
    ),
    (
        "conversation_gpu_lock",
        [
            ("build pc dùng rtx 4070 giá 50 triệu", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("hãy tối ưu cpu và main", [("cpu", "?"), ("mainboard", "?")]),
        ]
    ),
    (
        "conversation_replace_cpu",
        [
            ("build pc 35 triệu làm ai", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("đổi cpu sang ryzen 9 7950x", [("cao hơn ngân sách", "tăng ngân sách", "cpu", "mâu thuẫn", "?")]),
            ("ok 55 triệu đi", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("quay lại intel", [("cpu", "?"), ("mainboard", "?")]),
        ]
    ),
    (
        "conversation_replace_gpu",
        [
            ("build pc 35 triệu chơi game", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("đổi sang rtx 4080", [("cao hơn ngân sách", "tăng ngân sách", "mâu thuẫn", "?")]),
            ("ok 55 triệu đi", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
        ]
    ),
    (
        "conversation_invalid_compat",
        [
            ("build bộ pc dùng i9 14900k giá 40 triệu", [("chưa có", "không tìm", "chưa tìm", "không tìm thấy", "chưa có linh kiện", "?")]),
            ("đổi sang rtx 5090", [("chưa có", "không tìm", "chưa tìm", "không tìm thấy", "chưa có linh kiện", "?")]),
        ]
    ),
    (
        "conversation_upgrade",
        [
            ("build bộ pc 25 triệu làm data nặng ", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("nâng cấp cpu", [("cpu", "?")]),
            ("nâng cấp gpu", [("gpu", "?")]),
        ]
    ),
    (
        "conversation_reasoning",
        [
            ("build pc 30 triệu chơi game valorant", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("ưu tiên gpu hơn cpu", [("gpu", "?")]),
            ("ưu tiên cpu hơn gpu", [("cpu", "?")]),
        ]
    ),
    (
        "conversation_missing_context",
        [
            ("build pc", [("?", "- mã bộ:")]),
        ]
    ),
    (
        "conversation_compare",
        [
            ("build pc intel 30 triệu chơi game", [("cpu", "?"), ("gpu", "?"), ("mainboard", "?")]),
            ("đổi sang amd", [("cpu", "?"), ("mainboard", "?")]),
            ("quay lại intel", [("cpu", "?"), ("mainboard", "?")]),
        ]
    ),
]

_cleared_sessions = set()
_test_results = []

_TRAILING_ZERO_DECIMAL = re.compile(r'^(\d+)\.(0*)$')


def _session_id_for(label: str) -> str:
    return f"test_pc_build_{label}"


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
    scored = [r for r in _test_results if r["counts"]]
    total = len(scored)
    passed = sum(1 for r in scored if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    md_content = f"""# 🚀 Báo Cáo Kiểm Thử Tích Hợp API - PC Builder Multi-turn

Mỗi dòng là đúng một request được khai báo trong test và reply trực tiếp từ `/chat`.
Không tự trả lời clarification, không tự tăng ngân sách và không thay câu hỏi trước khi ghi báo cáo.

## 📊 Thống kê (chỉ tính các lượt được chấm điểm chính thức)
- **Tổng số lượt được chấm điểm:** {total}
- **Thành công (PASS):** {passed}
- **Thất bại (FAIL):** {failed}
- **Tỷ lệ thành công:** {pass_rate:.1f}%

## 📋 Chi tiết toàn bộ request/response

| # | Nhóm / Label | Session ID | Câu hỏi gửi lên | Phản hồi từ Bot | Từ khóa mong đợi | Kết quả |
|---|---|---|---|---|---|---|
"""
    for idx, r in enumerate(_test_results, 1):
        if r["counts"]:
            status = "✅ PASS" if r["passed"] else f"❌ FAIL<br>Thiếu: `{r['missing']}`"
        else:
            status = "ℹ️ INFO"
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


def _missing_keywords(expected_keywords, reply_lower: str) -> list:
    return [req for req in expected_keywords if not _check_requirement(req, reply_lower)]


def _send(session_id: str, question: str) -> str:
    payload = {"user_message": question, "session_id": session_id}
    try:
        response = requests.post(API_URL, json=payload, timeout=90, headers=get_auth_headers())
        if response.status_code not in (200, 201):
            return f"❌ LỖI API: HTTP {response.status_code} - {response.text}"
        return _extract_reply(response.json())
    except Exception as e:
        return f"❌ LỖI KẾT NỐI: Exception: {str(e)}"


def _log(label, session_id, question, reply, expected_keywords=None,
         counts=False, note="(thông tin, không chấm điểm)"):
    if expected_keywords is None:
        _test_results.append({
            "label": label, "session_id": session_id, "question": question,
            "reply": reply, "expected": note,
            "passed": True, "missing": "", "counts": False,
        })
        _update_md_report()
        return True, ""

    reply_lower = reply.lower()
    missing = _missing_keywords(expected_keywords, reply_lower)
    passed = len(missing) == 0
    missing_display = ", ".join(_format_requirement(m) for m in missing)
    _test_results.append({
        "label": label, "session_id": session_id, "question": question,
        "reply": reply,
        "expected": ", ".join(_format_requirement(r) for r in expected_keywords),
        "passed": passed, "missing": missing_display, "counts": counts,
    })
    _update_md_report()
    return passed, missing_display


@pytest.mark.live_llm
@pytest.mark.parametrize("label, turns", MULTI_TURN_CASES)
def test_multi_turn_pc_builder(label, turns):
    session_id = _session_id_for(label)
    _ensure_clean_session(session_id)

    for turn_idx, (question, expected_keywords) in enumerate(turns, 1):
        print(f"\n▶ [Turn {turn_idx}] Gửi: {question}")
        reply = _send(session_id, question)

        passed, missing_display = _log(
            f"{label} [Turn {turn_idx}]", session_id, question, reply,
            expected_keywords=expected_keywords, counts=True,
        )
        assert passed, f"[Turn {turn_idx}] Thiếu {missing_display} trong câu trả lời: '{reply}'"
