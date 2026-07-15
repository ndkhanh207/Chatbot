import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from utils import get_auth_headers
import os
import sys
import asyncio
import json
import pytest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
import pandas as pd

# Thêm đường dẫn gốc của project vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.api.chat import router as chat_router
from app.api.api_handler import chat_services
from app.api.api_handler.chat_services import process_chat_message
from app.api.model.chat_models import ChatRequest, EvalChatResponse
from config.config import Config
from main import http_exception_handler, unhandled_exception_handler, validation_exception_handler

REPORT_FILE = "tests/reports/report_restful_chat_api.md"

# Khởi tạo TestClient nội bộ để kiểm thử API độc lập không cần chạy Uvicorn
mock_app = FastAPI()
mock_app.include_router(chat_router)
mock_app.add_exception_handler(RequestValidationError, validation_exception_handler)
mock_app.add_exception_handler(StarletteHTTPException, http_exception_handler)
mock_app.add_exception_handler(Exception, unhandled_exception_handler)
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

Kiểm thử REST API, Firebase Auth, validation, timeout, session lock, hàng đợi và giới hạn hai model request chạy song song.

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


@pytest.fixture(autouse=True)
def restore_chat_concurrency_state():
    original_slots = chat_services._MODEL_REQUEST_SLOTS
    yield
    chat_services._MODEL_REQUEST_SLOTS = original_slots
    chat_services.PROCESSING_SESSIONS.clear()


def test_empty_message_validation():
    """Whitespace-only messages fail at the request schema."""
    payload = {"user_message": "   ", "session_id": "test_session_1"}
    resp_body = ""
    try:
        response = client.post("/chat", json=payload, headers=get_auth_headers())
        data = response.json()
        resp_body = json.dumps(data, ensure_ascii=False)
        passed = (response.status_code == 422 and data.get("code") == "INVALID_MESSAGE")
        err = "None" if passed else f"Unexpected response: {data}"
        status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_empty_message_validation",
        "description": "Gửi tin nhắn rỗng (bị bỏ trống)",
        "input": str(payload),
        "expected_status": 422,
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
        passed = (response.status_code == 422 and data.get("code") == "INVALID_SESSION_ID")
        err = "None" if passed else f"Unexpected response: {data}"
        status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_invalid_session_id_validation",
        "description": "Session ID chứa ký tự cấm (@, #, !!!)",
        "input": str(payload),
        "expected_status": 422,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_invalid_session_id_validation: {err}"

def test_request_length_contract():
    payload = {"user_message": "A" * 501, "session_id": "length_test"}
    response = client.post("/chat", json=payload, headers=get_auth_headers())
    body = response.json()
    passed = response.status_code == 422 and body.get("code") == "INVALID_MESSAGE"
    _test_results.append({
        "name": "test_request_length_contract",
        "description": "Tin nhắn vượt giới hạn public contract 500 ký tự",
        "input": "501 characters",
        "expected_status": 422,
        "actual_status": response.status_code,
        "response_body": json.dumps(body, ensure_ascii=False),
        "passed": passed,
        "error": "None" if passed else str(body),
    })
    _update_md_report()
    assert passed


def test_valid_chat_request():
    """Valid chat returns the exact public response contract."""
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
            passed = (response.status_code == 200 and data == {"chatbot_reply": "Dạ em chào bạn!"})
            err = "None" if passed else f"Unexpected response: {data}"
            status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_valid_chat_request",
        "description": "Gửi tin nhắn hợp lệ tới AI Bot (Bypass DB)",
        "input": str(payload),
        "expected_status": 200,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_valid_chat_request: {err}"

def test_eval_contract_uses_header_and_returns_contexts():
    payload = {"user_message": "Đánh giá RAG", "session_id": "eval_session"}

    async def mock_eval(*args, **kwargs):
        return EvalChatResponse(chatbot_reply="answer", contexts=["context-1"])

    with patch("app.api.chat.process_chat_message", side_effect=mock_eval):
        response = client.post(
            "/chat/eval",
            json=payload,
            headers={**get_auth_headers(), "X-Eval-Key": Config.RAGAS_MAGIC_KEY},
        )

    body = response.json()
    passed = response.status_code == 200 and body == {
        "chatbot_reply": "answer",
        "contexts": ["context-1"],
    }
    _test_results.append({
        "name": "test_eval_contract_uses_header_and_returns_contexts",
        "description": "Eval key nằm trong header và response có contexts",
        "input": "POST /chat/eval + X-Eval-Key",
        "expected_status": 200,
        "actual_status": response.status_code,
        "response_body": json.dumps(body, ensure_ascii=False),
        "passed": passed,
        "error": "None" if passed else str(body),
    })
    _update_md_report()
    assert passed


def test_eval_rejects_missing_key_with_structured_error():
    response = client.post(
        "/chat/eval",
        json={"user_message": "Đánh giá RAG", "session_id": "eval_forbidden"},
        headers=get_auth_headers(),
    )
    body = response.json()
    passed = response.status_code == 403 and body.get("code") == "INVALID_EVAL_KEY"
    _test_results.append({
        "name": "test_eval_rejects_missing_key_with_structured_error",
        "description": "Eval endpoint từ chối request thiếu X-Eval-Key",
        "input": "POST /chat/eval without X-Eval-Key",
        "expected_status": 403,
        "actual_status": response.status_code,
        "response_body": json.dumps(body, ensure_ascii=False),
        "passed": passed,
        "error": "None" if passed else str(body),
    })
    _update_md_report()
    assert passed


def test_missing_auth_uses_public_error_contract():
    response = client.post(
        "/chat",
        json={"user_message": "hello", "session_id": "auth_test"},
    )
    body = response.json()
    passed = response.status_code == 401 and body == {
        "error": "Authentication Error",
        "message": "Bearer token is required.",
        "code": "AUTH_REQUIRED",
    }
    _test_results.append({
        "name": "test_missing_auth_uses_public_error_contract",
        "description": "Lỗi authentication dùng cùng ErrorResponse schema",
        "input": "POST /chat without Authorization",
        "expected_status": 401,
        "actual_status": response.status_code,
        "response_body": json.dumps(body, ensure_ascii=False),
        "passed": passed,
        "error": "None" if passed else str(body),
    })
    _update_md_report()
    assert passed


def test_llm_generation_timeout_504():
    """Tình huống 4: Mô phỏng AI xử lý quá lâu (Timeout) -> Kỳ vọng mã 504 LLM_GENERATION_TIMEOUT."""
    payload = {"user_message": "Tư vấn cấu hình PC chi tiết", "session_id": "test_timeout_session"}
    resp_body = ""
    
    async def mock_process_chat_message_timeout(*args, **kwargs):
        raise asyncio.TimeoutError("Simulated LLM Timeout")

    try:
        with patch("app.api.api_handler.chat_services.handle_chat", side_effect=mock_process_chat_message_timeout):
            response = client.post("/chat", json=payload, headers=get_auth_headers())
            data = response.json()
            resp_body = json.dumps(data, ensure_ascii=False)
            passed = (response.status_code == 504 and data.get("code") == "LLM_GENERATION_TIMEOUT")
            err = "None" if passed else f"Unexpected response: {data}"
            status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_llm_generation_timeout_504",
        "description": "Mô phỏng AI xử lý quá lâu",
        "input": str(payload),
        "expected_status": 504,
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
    
    async def mock_process_chat_message_500(*args, **kwargs):
        raise Exception("Simulated Database / LLM Exception")

    try:
        with patch("app.api.api_handler.chat_services.handle_chat", side_effect=mock_process_chat_message_500):
            response = client.post("/chat", json=payload, headers=get_auth_headers())
            data = response.json()
            resp_body = json.dumps(data, ensure_ascii=False)
            passed = (response.status_code == 500 and data.get("code") == "INTERNAL_SERVER_ERROR")
            err = "None" if passed else f"Unexpected response: {data}"
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

def test_different_users_may_share_session_id():
    async def run_case():
        chat_services.PROCESSING_SESSIONS.clear()
        chat_services._MODEL_REQUEST_SLOTS = asyncio.Semaphore(2)
        fake_request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    knowledge_base=pd.DataFrame({"name": ["mock"]}),
                    vector_store=None,
                    build_data=None,
                )
            )
        )
        both_started = asyncio.Event()
        release = asyncio.Event()
        active = 0

        async def blocking_handle_chat(*args, **kwargs):
            nonlocal active
            active += 1
            if active == 2:
                both_started.set()
            await release.wait()
            return {"chatbot_reply": kwargs["user_uid"]}

        payload = ChatRequest(user_message="hello", session_id="shared_session")
        with patch("app.api.api_handler.chat_services.handle_chat", side_effect=blocking_handle_chat):
            user_a = asyncio.create_task(process_chat_message(fake_request, payload, "user_a"))
            user_b = asyncio.create_task(process_chat_message(fake_request, payload, "user_b"))
            await asyncio.wait_for(both_started.wait(), timeout=1)
            keys_while_active = set(chat_services.PROCESSING_SESSIONS)
            release.set()
            results = await asyncio.gather(user_a, user_b)

        return results, keys_while_active

    results, keys = asyncio.run(run_case())
    replies = [result.chatbot_reply for result in results]
    passed = replies == ["user_a", "user_b"] and keys == {
        "user_a:shared_session",
        "user_b:shared_session",
    }
    _test_results.append({
        "name": "test_different_users_may_share_session_id",
        "description": "Session lock được định danh bằng user UID và session ID",
        "input": "2 users / same session_id",
        "expected_status": "both accepted",
        "actual_status": "both accepted" if passed else "collision",
        "response_body": json.dumps({"replies": replies, "keys": sorted(keys)}),
        "passed": passed,
        "error": "None" if passed else f"replies={replies}, keys={keys}",
    })
    _update_md_report()
    assert passed


def test_busy_sessions_queue_without_model_overlap():
    """Different sessions wait; duplicate requests for one session still fail fast."""
    async def run_case():
        chat_services.PROCESSING_SESSIONS.clear()
        chat_services._MODEL_REQUEST_SLOTS = asyncio.Semaphore(1)

        fake_request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    knowledge_base=pd.DataFrame({"name": ["mock"]}),
                    vector_store=None,
                    build_data=None,
                )
            )
        )
        payload = ChatRequest(user_message="build pc 30 triệu chơi game", session_id="busy_session")
        other_payload = ChatRequest(user_message="rtx 4080 giá bao nhiêu", session_id="other_busy_session")

        first_started = asyncio.Event()
        release_first = asyncio.Event()
        active_calls = 0
        max_active_calls = 0
        call_order = []

        async def slow_handle_chat(*args, **kwargs):
            nonlocal active_calls, max_active_calls
            session_id = kwargs["session_id"]
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            call_order.append(session_id)
            try:
                if session_id == "busy_session":
                    first_started.set()
                    await release_first.wait()
                return {"chatbot_reply": session_id}
            finally:
                active_calls -= 1

        with patch("app.api.api_handler.chat_services.handle_chat", side_effect=slow_handle_chat):
            first = asyncio.create_task(process_chat_message(fake_request, payload, "test_user"))
            await asyncio.wait_for(first_started.wait(), timeout=1)
            second = await process_chat_message(fake_request, payload, "test_user")
            third = asyncio.create_task(process_chat_message(fake_request, other_payload, "test_user"))
            await asyncio.sleep(0)
            queued_while_busy = not third.done()
            release_first.set()
            first_result, third_result = await asyncio.gather(first, third)

        chat_services.PROCESSING_SESSIONS.clear()
        return first_result, second, third_result, queued_while_busy, max_active_calls, call_order

    first_result, second, third, queued_while_busy, max_active_calls, call_order = asyncio.run(run_case())
    second_body = json.loads(second.body.decode("utf-8"))

    passed = (
        first_result.chatbot_reply == "busy_session"
        and second.status_code == 429
        and second_body.get("code") == "SESSION_LOCKED"
        and third.chatbot_reply == "other_busy_session"
        and queued_while_busy
        and max_active_calls == 1
        and call_order == ["busy_session", "other_busy_session"]
    )
    _test_results.append({
        "name": "test_busy_session_returns_429",
        "description": "Gửi request thứ hai khi session đang xử lý",
        "input": "2 x POST /chat same session",
        "expected_status": 429,
        "actual_status": second.status_code,
        "response_body": json.dumps(
            {"same_session": second_body, "other_session": third.model_dump()},
            ensure_ascii=False,
        ),
        "passed": passed,
        "error": "None" if passed else f"Unexpected response: {second_body} / {third}",
    })
    _update_md_report()
    assert passed, f"Queue failed: {second_body} / {third} / {call_order}"


def test_model_allows_two_parallel_requests_and_queues_third():
    async def run_case():
        chat_services.PROCESSING_SESSIONS.clear()
        chat_services._MODEL_REQUEST_SLOTS = asyncio.Semaphore(chat_services.Config.MAX_PARALLEL_REQUESTS)
        fake_request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(knowledge_base=pd.DataFrame({"name": ["mock"]}), vector_store=None, build_data=None)
            )
        )
        two_started = asyncio.Event()
        release_requests = asyncio.Event()
        active_calls = 0
        max_active_calls = 0

        async def blocking_handle_chat(*args, **kwargs):
            nonlocal active_calls, max_active_calls
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            if active_calls == 2:
                two_started.set()
            try:
                await release_requests.wait()
                return {"chatbot_reply": kwargs["session_id"]}
            finally:
                active_calls -= 1

        payloads = [
            ChatRequest(user_message=f"request {index}", session_id=f"parallel_{index}")
            for index in range(3)
        ]
        with patch("app.api.api_handler.chat_services.handle_chat", side_effect=blocking_handle_chat):
            first = asyncio.create_task(process_chat_message(fake_request, payloads[0], "test_user"))
            second = asyncio.create_task(process_chat_message(fake_request, payloads[1], "test_user"))
            await asyncio.wait_for(two_started.wait(), timeout=1)
            third = asyncio.create_task(process_chat_message(fake_request, payloads[2], "test_user"))
            await asyncio.sleep(0)
            third_queued = not third.done()
            release_requests.set()
            results = await asyncio.gather(first, second, third)

        chat_services.PROCESSING_SESSIONS.clear()
        return results, third_queued, max_active_calls

    results, third_queued, max_active_calls = asyncio.run(run_case())
    replies = [result.chatbot_reply for result in results]
    passed = (
        chat_services.Config.MAX_PARALLEL_REQUESTS == 2
        and replies == ["parallel_0", "parallel_1", "parallel_2"]
        and third_queued
        and max_active_calls == 2
    )
    _test_results.append({
        "name": "test_model_allows_two_parallel_requests_and_queues_third",
        "description": "Hai request chạy song song, request thứ ba chờ slot",
        "input": "3 sessions / 2 model slots",
        "expected_status": "max_active=2",
        "actual_status": f"max_active={max_active_calls}",
        "response_body": json.dumps({"replies": replies, "third_queued": third_queued}),
        "passed": passed,
        "error": "None" if passed else f"replies={replies}, queued={third_queued}",
    })
    _update_md_report()
    assert passed


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [(asyncio.TimeoutError(), 504), (RuntimeError("boom"), 500)],
)
def test_model_queue_releases_after_failure(failure, expected_status):
    async def run_case():
        chat_services.PROCESSING_SESSIONS.clear()
        chat_services._MODEL_REQUEST_SLOTS = asyncio.Semaphore(1)
        fake_request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(knowledge_base=pd.DataFrame({"name": ["mock"]}), vector_store=None, build_data=None)
            )
        )
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        call_count = 0

        async def failing_then_succeeding_handle_chat(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                first_started.set()
                await release_first.wait()
                raise failure
            return {"chatbot_reply": "recovered"}

        first_payload = ChatRequest(user_message="first", session_id="failure_session")
        next_payload = ChatRequest(user_message="next", session_id="next_session")
        with patch(
            "app.api.api_handler.chat_services.handle_chat",
            side_effect=failing_then_succeeding_handle_chat,
        ):
            first = asyncio.create_task(process_chat_message(fake_request, first_payload, "test_user"))
            await asyncio.wait_for(first_started.wait(), timeout=1)
            next_request = asyncio.create_task(process_chat_message(fake_request, next_payload, "test_user"))
            await asyncio.sleep(0)
            queued_while_busy = not next_request.done()
            release_first.set()
            first_result, next_result = await asyncio.gather(first, next_request)

        chat_services.PROCESSING_SESSIONS.clear()
        return first_result, next_result, queued_while_busy

    first_result, next_result, queued_while_busy = asyncio.run(run_case())
    passed = (
        first_result.status_code == expected_status
        and next_result.chatbot_reply == "recovered"
        and queued_while_busy
    )
    failure_name = type(failure).__name__
    _test_results.append({
        "name": f"test_model_queue_releases_after_{failure_name}",
        "description": "Slot được nhả sau timeout/lỗi để request tiếp theo chạy",
        "input": failure_name,
        "expected_status": f"{expected_status}, then success",
        "actual_status": f"{first_result.status_code}, then success",
        "response_body": json.dumps(next_result.model_dump()),
        "passed": passed,
        "error": "None" if passed else f"next={next_result}, queued={queued_while_busy}",
    })
    _update_md_report()
    assert passed


def test_processing_timeout_cancels_only_stuck_request():
    async def run_case():
        chat_services._MODEL_REQUEST_SLOTS = asyncio.Semaphore(2)
        fake_request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(knowledge_base=pd.DataFrame({"name": ["mock"]}), vector_store=None, build_data=None)
            )
        )
        stuck_cancelled = asyncio.Event()

        async def one_stuck_one_normal(*args, **kwargs):
            if kwargs["session_id"] == "stuck_session":
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    stuck_cancelled.set()
                    raise
            return {"chatbot_reply": "normal completed"}

        stuck_payload = ChatRequest(user_message="stuck", session_id="stuck_session")
        normal_payload = ChatRequest(user_message="normal", session_id="normal_session")
        with (
            patch("app.api.api_handler.chat_services.handle_chat", side_effect=one_stuck_one_normal),
            patch("app.api.api_handler.chat_services.Config.MODEL_PROCESSING_TIMEOUT_SECONDS", 0.05),
        ):
            stuck, normal = await asyncio.gather(
                process_chat_message(fake_request, stuck_payload, "test_user"),
                process_chat_message(fake_request, normal_payload, "test_user"),
            )

        return stuck, normal, stuck_cancelled.is_set()

    stuck, normal, stuck_cancelled = asyncio.run(run_case())
    passed = (
        stuck.status_code == 504
        and normal.chatbot_reply == "normal completed"
        and stuck_cancelled
    )
    _test_results.append({
        "name": "test_processing_timeout_cancels_only_stuck_request",
        "description": "Timeout chỉ hủy request treo, request song song vẫn hoàn tất",
        "input": "1 stuck + 1 normal request",
        "expected_status": "504 + success",
        "actual_status": f"{stuck.status_code} + success",
        "response_body": json.dumps(normal.model_dump()),
        "passed": passed,
        "error": "None" if passed else f"normal={normal}, cancelled={stuck_cancelled}",
    })
    _update_md_report()
    assert passed


def test_model_queue_returns_429_after_5_seconds():
    async def run_case():
        chat_services.PROCESSING_SESSIONS.clear()
        chat_services._MODEL_REQUEST_SLOTS = asyncio.Semaphore(1)
        fake_request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(knowledge_base=pd.DataFrame({"name": ["mock"]}), vector_store=None, build_data=None)
            )
        )
        first_started = asyncio.Event()
        release_first = asyncio.Event()

        async def slow_handle_chat(*args, **kwargs):
            first_started.set()
            await release_first.wait()
            return {"chatbot_reply": "ok"}

        first_payload = ChatRequest(user_message="first", session_id="active_session")
        waiting_payload = ChatRequest(user_message="waiting", session_id="waiting_session")
        with (
            patch("app.api.api_handler.chat_services.handle_chat", side_effect=slow_handle_chat),
            patch("app.api.api_handler.chat_services.Config.MODEL_QUEUE_TIMEOUT_SECONDS", 0.01),
        ):
            first = asyncio.create_task(process_chat_message(fake_request, first_payload, "test_user"))
            await asyncio.wait_for(first_started.wait(), timeout=1)
            timed_out = await process_chat_message(fake_request, waiting_payload, "test_user")
            waiting_session_released = "test_user:waiting_session" not in chat_services.PROCESSING_SESSIONS
            release_first.set()
            await first

        chat_services.PROCESSING_SESSIONS.clear()
        return timed_out, waiting_session_released

    response, waiting_session_released = asyncio.run(run_case())
    body = json.loads(response.body.decode("utf-8"))
    passed = (
        response.status_code == 429
        and body["code"] == "MODEL_QUEUE_TIMEOUT"
        and waiting_session_released
    )
    _test_results.append({
        "name": "test_model_queue_returns_429_after_5_seconds",
        "description": "Queue quá 5 giây trả 429 và nhả session slot",
        "input": "model busy beyond queue timeout",
        "expected_status": 429,
        "actual_status": response.status_code,
        "response_body": json.dumps(body, ensure_ascii=False),
        "passed": passed,
        "error": "None" if passed else f"body={body}, released={waiting_session_released}",
    })
    _update_md_report()
    assert passed


def test_openapi_documents_public_response_contracts():
    schema = mock_app.openapi()
    chat_responses = schema["paths"]["/chat"]["post"]["responses"]
    chat_schema = chat_responses["200"]["content"]["application/json"]["schema"]
    eval_schema = schema["paths"]["/chat/eval"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    embedding_schema = schema["paths"]["/v1/embeddings"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    delete_schema = schema["paths"]["/sessions/{session_id}"]["delete"]["responses"]["200"]["content"]["application/json"]["schema"]
    passed = (
        chat_schema.get("$ref", "").endswith("/ChatResponse")
        and eval_schema.get("$ref", "").endswith("/EvalChatResponse")
        and embedding_schema.get("$ref", "").endswith("/EmbeddingResponse")
        and delete_schema.get("$ref", "").endswith("/DeleteSessionResponse")
        and "201" not in chat_responses
        and {"401", "403", "422", "429", "500", "503", "504"} <= set(chat_responses)
    )
    _test_results.append({
        "name": "test_openapi_documents_public_response_contracts",
        "description": "OpenAPI mô tả response models và status codes công khai",
        "input": "GET /openapi.json (in-process)",
        "expected_status": "schemas documented",
        "actual_status": "schemas documented" if passed else "schema mismatch",
        "response_body": json.dumps({"chat_statuses": sorted(chat_responses)}),
        "passed": passed,
        "error": "None" if passed else "OpenAPI response contract mismatch",
    })
    _update_md_report()
    assert passed

def test_delete_session_history():
    """Tình huống 6: Xóa lịch sử phiên hội thoại -> Kỳ vọng mã 200 OK."""
    session_id = "test_valid_session"
    url = f"/sessions/{session_id}"
    resp_body = ""
    try:
        # Mock clear_session để tránh kết nối MySQL trong TestClient
        with patch("app.api.chat.ConversationContext.clear"):
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
