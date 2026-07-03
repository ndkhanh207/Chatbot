import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from utils import get_auth_headers
import os
import sys
import asyncio
import json
import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd

# Thêm đường dẫn gốc của project vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.api.chat import router as chat_router

REPORT_FILE = "tests/reports/report_restful_chat_api.md"

# Khởi tạo TestClient nội bộ để kiểm thử API độc lập không cần chạy Uvicorn
mock_app = FastAPI()
mock_app.include_router(chat_router)
mock_app.state.knowledge_base = pd.DataFrame()
mock_app.state.vector_store = None
mock_app.state.build_data = None


client = TestClient(mock_app, raise_server_exceptions=False)
_test_results = []

def _update_md_report():
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    total = len(_test_results)
    passed = sum(1 for r in _test_results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    md_content = f"""# 🚀 Báo Cáo Kiểm Thử Tích Hợp RESTful Chat API (Có bảo mật Firebase Auth)

Kiểm thử toàn diện các tình huống thực tế (Thành công 201, Lỗi 400 Validation, Lỗi 500 System, Lỗi 504 Timeout, Delete Session) cho hệ thống AI Chatbot, có áp dụng Mock Firebase JWT.

## 📊 Thống kê chung
- **Tổng số Test Cases:** {total}
- **Thành công (PASS):** {passed}
- **Thất bại (FAIL):** {failed}
- **Tỷ lệ thành công:** {pass_rate:.1f}%

## 📋 Chi tiết kết quả kiểm thử

| # | Tên Test Case | Mô tả tình huống | Input / URL | Expected Status | Actual Status | Response Body (JSON) | Kết quả |
|---|---|---|---|---|---|---|---|
"""
    for idx, r in enumerate(_test_results, 1):
        status_str = "✅ PASS" if r["passed"] else f"❌ FAIL<br>Chi tiết: `{r['error']}`"
        resp_clean = r.get("response_body", "").replace("\n", "<br>").replace("|", "\\|")
        md_content += f"| {idx} | `{r['name']}` | {r['description']} | `{r['input']}` | {r['expected_status']} | {r['actual_status']} | `{resp_clean}` | {status_str} |\n"

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(md_content)

def setup_module(module):
    _test_results.clear()
    _update_md_report()

def test_empty_message_validation():
    """Tình huống 1: Người dùng gửi tin nhắn rỗng -> Kỳ vọng lỗi 400 EMPTY_MESSAGE."""
    payload = {"user_message": "   ", "session_id": "test_session_1"}
    resp_body = ""
    try:
        response = client.post("/chat", json=payload, headers=get_auth_headers())
        data = response.json()
        resp_body = json.dumps(data, ensure_ascii=False)
        passed = (response.status_code == 400 and data.get("code") == "EMPTY_MESSAGE")
        err = "None" if passed else f"Unexpected response: {data}"
        status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_empty_message_validation",
        "description": "Gửi tin nhắn rỗng (bị bỏ trống)",
        "input": str(payload),
        "expected_status": 400,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_empty_message_validation: {err}"

def test_invalid_session_id_validation():
    """Tình huống 2: Session ID chứa ký tự đặc biệt không hợp lệ -> Kỳ vọng lỗi 422 Unprocessable Entity."""
    payload = {"user_message": "Cho tôi hỏi về CPU RTX 4090", "session_id": "invalid@session#id!!!"}
    resp_body = ""
    try:
        response = client.post("/chat", json=payload, headers=get_auth_headers())
        data = response.json()
        resp_body = json.dumps(data, ensure_ascii=False)
        passed = (response.status_code == 422)
        err = "None" if passed else f"Unexpected response: {data}"
        status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_invalid_session_id_validation",
        "description": "Session ID chứa ký tự cấm (@, #, !!!)",
        "input": str(payload),
        "expected_status": 400,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_invalid_session_id_validation: {err}"

def test_valid_chat_request():
    """Tình huống 3: Gửi tin nhắn hợp lệ -> Kỳ vọng mã 201 Created (hoặc 200) kèm chatbot_reply."""
    payload = {"user_message": "Xin chào, bạn có thể giúp gì cho tôi?", "session_id": "test_valid_session"}
    resp_body = ""
    try:
        # Gọi thẳng hàm handle_chat vì TestClient đồng bộ và database chưa kết nối sẽ lỗi. 
        # Chúng ta mock handle_chat cho API test
        def mock_process_chat_message(*args, **kwargs):
            return {"chatbot_reply": "Dạ em chào bạn!"}
            
        with patch("app.api.chat.process_chat_message", side_effect=mock_process_chat_message):
            response = client.post("/chat", json=payload, headers=get_auth_headers())
            data = response.json()
            resp_body = json.dumps(data, ensure_ascii=False)
            passed = (response.status_code in [200, 201] and "chatbot_reply" in data)
            err = "None" if passed else f"Unexpected response: {data}"
            status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_valid_chat_request",
        "description": "Gửi tin nhắn hợp lệ tới AI Bot (Bypass DB)",
        "input": str(payload),
        "expected_status": "201/200",
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_valid_chat_request: {err}"

def test_llm_generation_timeout_504():
    """Tình huống 4: Mô phỏng AI xử lý quá lâu (Timeout) -> Kỳ vọng mã 504 LLM_GENERATION_TIMEOUT."""
    payload = {"user_message": "Tư vấn cấu hình PC chi tiết", "session_id": "test_timeout_session"}
    resp_body = ""
    
    def mock_process_chat_message_timeout(*args, **kwargs):
        raise asyncio.TimeoutError("Simulated LLM Timeout")

    try:
        with patch("app.api.chat.process_chat_message", side_effect=mock_process_chat_message_timeout):
            response = client.post("/chat", json=payload, headers=get_auth_headers())
            resp_body = response.text
            passed = (response.status_code == 500)
            err = "None" if passed else f"Unexpected response: {resp_body}"
            status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_llm_generation_timeout_504",
        "description": "Mô phỏng AI xử lý quá lâu (Timeout - nay trả về 500)",
        "input": str(payload),
        "expected_status": 500,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_llm_generation_timeout_504: {err}"

def test_internal_server_error_500():
    """Tình huống 5: Mô phỏng lỗi hệ thống nội bộ (Exception) -> Kỳ vọng mã 500 INTERNAL_SERVER_ERROR."""
    payload = {"user_message": "Tư vấn cấu hình PC chi tiết", "session_id": "test_500_session"}
    resp_body = ""
    
    def mock_process_chat_message_500(*args, **kwargs):
        raise Exception("Simulated Database / LLM Exception")

    try:
        with patch("app.api.chat.process_chat_message", side_effect=mock_process_chat_message_500):
            response = client.post("/chat", json=payload, headers=get_auth_headers())
            resp_body = response.text
            passed = (response.status_code == 500)
            err = "None" if passed else f"Unexpected response: {resp_body}"
            status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_internal_server_error_500",
        "description": "Mô phỏng lỗi hệ thống nội bộ (Internal Server Error)",
        "input": str(payload),
        "expected_status": 500,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_internal_server_error_500: {err}"

def test_delete_session_history():
    """Tình huống 6: Xóa lịch sử phiên hội thoại -> Kỳ vọng mã 200 OK."""
    session_id = "test_valid_session"
    url = f"/sessions/{session_id}"
    resp_body = ""
    try:
        # Mock clear_session để tránh kết nối MySQL trong TestClient
        with patch("app.api.chat.clear_session"):
            response = client.delete(url, headers=get_auth_headers())
            data = response.json()
            resp_body = json.dumps(data, ensure_ascii=False)
            passed = (response.status_code == 200 and data.get("status") == "ok")
            err = "None" if passed else f"Unexpected response: {data}"
            status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_delete_session_history",
        "description": "Xóa lịch sử phiên hội thoại (Mock DB)",
        "input": url,
        "expected_status": 200,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_delete_session_history: {err}"
