import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from utils import get_auth_headers
import pytest
import requests
import re
import math

API_URL = "http://127.0.0.1:8000/chat"
SESSION_API_BASE = "http://127.0.0.1:8000/sessions"
REPORT_FILE = "tests/reports/report_pc_builder_multi_turn_api.md"
MAX_AUTO_ROUNDS = 6

MULTI_TURN_CASES = [
    (
        "conversation_budget",
        [
            ("build pc 30 triệu chơi game", ["cpu", "gpu", "mainboard"]),
            ("tăng ngân sách lên 35 triệu", ["cpu", "gpu", "mainboard"]),
            ("thôi chỉ còn 20 triệu", [("cao hơn ngân sách", "tăng ngân sách", "cpu")]),
        ]
    ),
    (
        "conversation_cpu_lock",
        [
            ("build pc 30 triệu làm văn phòng", ["cpu", "gpu", "mainboard"]),
            ("giữ nguyên cpu nhưng đổi sang rtx 4080", [("cao hơn ngân sách", "tăng ngân sách", "cpu")]),
            ("ok 50 triệu đi", ["cpu", "gpu", "mainboard"]),
            ("giữ nguyên gpu nhưng đổi sang main z790", ["cpu", "gpu", "mainboard"]),
        ]
    ),
    (
        "conversation_gpu_lock",
        [
            ("build pc dùng rtx 4070 giá 50 triệu", ["cpu", "gpu", "mainboard"]),
            ("hãy tối ưu cpu và main", ["cpu", "mainboard"]),
        ]
    ),
    (
        "conversation_replace_cpu",
        [
            ("build pc 35 triệu làm ai", ["cpu", "gpu", "mainboard"]),
            ("đổi cpu sang ryzen 9 7950x", [("cao hơn ngân sách", "tăng ngân sách", "cpu")]),
            ("ok 55 triệu đi", ["cpu", "gpu", "mainboard"]),
            ("quay lại intel", ["cpu", "mainboard"]),
        ]
    ),
    (
        "conversation_replace_gpu",
        [
            ("build pc 35 triệu chơi game", ["cpu", "gpu", "mainboard"]),
            ("đổi sang rtx 4080", ["cao hơn ngân sách", "tăng ngân sách"]),
            ("ok 55 triệu đi", ["cpu", "gpu", "mainboard"]),
        ]
    ),
    (
        "conversation_invalid_compat",
        [
            ("build bộ pc dùng i9 14900k giá 40 triệu", ["cpu", "gpu", "mainboard"]),
            ("đổi sang rtx 5090", [("chưa có", "không tìm")]),
            ("ok gợi ý đi", ["cpu", "gpu", "mainboard"]),
        ]
    ),
    (
        "conversation_upgrade",
        [
            ("build bộ pc 25 triệu làm data nặng ", ["cpu", "gpu", "mainboard"]),
            ("nâng cấp cpu", ["cpu"]),
            ("nâng cấp gpu", ["gpu"]),
        ]
    ),
    (
        "conversation_reasoning",
        [
            ("build pc 30 triệu chơi game valorant", ["cpu", "gpu", "mainboard"]),
            ("ưu tiên gpu hơn cpu", ["gpu"]),
            ("ưu tiên cpu hơn gpu", ["cpu"]),
        ]
    ),
    (
        "conversation_missing_context",
        [
            ("build pc", [("ngân sách", "bao nhiêu tiền", "khoảng", "đầu tư", "tầm giá")]),
            ("30 triệu", [("làm gì", "mục đích", "nhu cầu", "chủ yếu")]),
            ("chơi game aaa", ["cpu", "gpu", "mainboard"]),
        ]
    ),
    (
        "conversation_compare",
        [
            ("build pc intel 30 triệu chơi game", ["cpu", "gpu", "mainboard"]),
            ("đổi sang amd", ["cpu", "mainboard"]),
            ("quay lại intel", ["cpu", "mainboard"]),
        ]
    ),
]

_cleared_sessions = set()
_test_results = []
_session_budget: dict[str, str] = {}

_TRAILING_ZERO_DECIMAL = re.compile(r'^(\d+)\.(0*)$')
_AMOUNT_PATTERN = re.compile(r'(\d+(?:[.,]\d+)?)\s*tri[eệ]u', re.IGNORECASE)
_PRICE_HINT_PATTERN = re.compile(
    r'giá\s*(?:khoảng|thấp nhất|rẻ nhất)?\s*(\d+(?:[.,]\d+)?)\s*tri[eệ]u', re.IGNORECASE
)
# Trạng thái "hết hàng nhưng còn hướng đi tiếp" — bot xin phép trước khi gợi ý phương án thay thế.
# Khác với terminal thật sự (không có gì để đi tiếp) ở chỗ nó LUÔN kèm một câu hỏi mời gợi ý khác.
_STOCK_UNAVAILABLE_PATTERN = re.compile(r'chưa có|không có sẵn|hết hàng', re.IGNORECASE)
_OFFER_ALTERNATIVE_PATTERN = re.compile(
    r'(có muốn|muốn em|bạn muốn).*(gợi ý|thay thế|gần nhất|tương tự|phương án)', re.IGNORECASE
)


def _session_id_for(label: str) -> str:
    return f"test_pc_build_{label}"


def _ensure_clean_session(session_id: str):
    if session_id in _cleared_sessions:
        return
    try:
        requests.delete(f"{SESSION_API_BASE}/{session_id}", timeout=10, headers=get_auth_headers())
    except requests.RequestException:
        pass
    _cleared_sessions.add(session_id)
    _session_budget.pop(session_id, None)


def _remember_budget(session_id: str, text: str):
    m = _AMOUNT_PATTERN.search(text)
    if m:
        _session_budget[session_id] = m.group(1).replace(',', '.')


def _current_budget(session_id: str, default: str = "30") -> str:
    return _session_budget.get(session_id, default)


def _extract_suggested_amount(reply: str) -> float | None:
    m = _PRICE_HINT_PATTERN.search(reply) or _AMOUNT_PATTERN.search(reply)
    if not m:
        return None
    return float(m.group(1).replace(',', '.'))


def _is_budget_question(reply_lower: str) -> bool:
    return 'bao nhiêu tiền' in reply_lower


def _is_purpose_question(reply_lower: str) -> bool:
    return 'để làm gì' in reply_lower or 'mục đích' in reply_lower


def _is_over_budget_prompt(reply_lower: str) -> bool:
    return 'cao hơn ngân sách' in reply_lower or 'tăng ngân sách' in reply_lower


def _is_stock_unavailable_with_offer(reply_lower: str) -> bool:
    """'Chưa có hàng' NHƯNG bot chủ động mời phương án khác -> đây là câu hỏi yes/no, phải trả lời tiếp, không phải điểm dừng."""
    return bool(_STOCK_UNAVAILABLE_PATTERN.search(reply_lower)) and bool(_OFFER_ALTERNATIVE_PATTERN.search(reply_lower))


def _is_terminal_not_found(reply_lower: str) -> bool:
    """Điểm dừng THẬT: không tìm thấy và không có gợi ý nào để đi tiếp."""
    return ('không tìm thấy' in reply_lower or 'chưa có' in reply_lower) and not _is_stock_unavailable_with_offer(reply_lower)


def _update_md_report():
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    scored = [r for r in _test_results if r["counts"]]
    total = len(scored)
    passed = sum(1 for r in scored if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    md_content = f"""# 🚀 Báo Cáo Kiểm Thử Tích Hợp API - PC Builder Multi-turn

Mọi request/response thực tế gửi tới `/chat` đều được liệt kê tường minh bên dưới, kể cả:
- các lượt bot hỏi mớm (ngân sách/mục đích),
- các lượt bot báo vượt ngân sách và được tự động tăng ngân sách lên một chút để thử lại,
- các lượt bot báo hết hàng nhưng mời phương án thay thế (tự động trả lời "có" để đi tiếp),

cho đến khi turn đó có kết quả thỏa yêu cầu, hoặc bot xác nhận một điểm dừng thật sự
(không tìm thấy và không còn phương án nào để gợi ý tiếp).
Không có bước nào bị gộp hay ghi đè âm thầm.
Dòng có cột **Kết quả = ℹ️ INFO** là bước trung gian, không tính vào tỷ lệ pass/fail.

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
    _remember_budget(session_id, question)
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


@pytest.mark.parametrize("label, turns", MULTI_TURN_CASES)
def test_multi_turn_pc_builder(label, turns):
    session_id = _session_id_for(label)
    _ensure_clean_session(session_id)

    for turn_idx, (question, expected_keywords) in enumerate(turns, 1):
        print(f"\n▶ [Turn {turn_idx}] Gửi: {question}")
        current_question = question
        reply = _send(session_id, current_question)

        for round_idx in range(MAX_AUTO_ROUNDS):
            reply_lower = reply.lower()

            if not _missing_keywords(expected_keywords, reply_lower):
                break  # đã thỏa yêu cầu của turn -> dừng, không mớm thêm

            if _is_over_budget_prompt(reply_lower):
                suggested = _extract_suggested_amount(reply)
                if suggested is None:
                    break
                new_budget = math.ceil(suggested) + 1
                _session_budget[session_id] = str(new_budget)
                next_question = f"ok tăng ngân sách lên {new_budget} triệu đi"
                note = f"(bot báo vượt ngân sách, tự động tăng thêm một chút lên {new_budget} triệu)"

            elif _is_budget_question(reply_lower):
                next_question = f"khoảng {_current_budget(session_id)} triệu"
                note = f"(bot hỏi lại ngân sách, tự động mớm theo ngân sách đã biết: {_current_budget(session_id)} triệu)"

            elif _is_purpose_question(reply_lower):
                next_question = "chơi game"
                note = "(bot hỏi lại mục đích, chưa chấm điểm)"

            elif _is_stock_unavailable_with_offer(reply_lower):
                # Đây là câu hỏi yes/no thật ("bạn có muốn em gợi ý ... không?") -> trả lời "có" để đi tiếp
                next_question = "Có, gợi ý giúp mình phương án gần nhất đi."
                note = "(bot báo hết hàng nhưng mời phương án thay thế, tự động trả lời 'có' để tiếp tục)"

            elif _is_terminal_not_found(reply_lower):
                break  # điểm dừng thật: không tìm thấy và không có phương án nào để đi tiếp

            else:
                break  # không nhận diện được dạng mớm nào -> dừng, để lộ đúng lỗi thật nếu có

            _log(f"{label} [Turn {turn_idx} - vòng {round_idx + 1}]", session_id,
                 current_question, reply, note=note)
            print(f"▶ [Turn {turn_idx} - vòng {round_idx + 1} - AUTO] Bơm: '{next_question}'")

            current_question = next_question
            reply = _send(session_id, current_question)

        passed, missing_display = _log(
            f"{label} [Turn {turn_idx}]", session_id, current_question, reply,
            expected_keywords=expected_keywords, counts=True,
        )
        assert passed, f"[Turn {turn_idx}] Thiếu {missing_display} trong câu trả lời: '{reply}'"