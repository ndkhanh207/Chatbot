# 🚀 Báo Cáo Kiểm Thử Tích Hợp RESTful Chat API (Có bảo mật Firebase Auth)

Kiểm thử REST API, Firebase Auth, validation, timeout, session lock, hàng đợi và giới hạn hai model request chạy song song.

## 📊 Thống kê chung
- **Tổng số Test Cases:** 18
- **Thành công (PASS):** 18
- **Thất bại (FAIL):** 0
- **Tỷ lệ thành công:** 100.0%

## 📋 Chi tiết kết quả kiểm thử

| # | Tên Test Case | Mô tả tình huống | Input / URL | Expected Status | Actual Status | Response Body (JSON) | Kết quả |
|---|---|---|---|---|---|---|---|
| 1 | `test_empty_message_validation` | Gửi tin nhắn rỗng (bị bỏ trống) | `{'user_message': '   ', 'session_id': 'test_session_1'}` | 422 | 422 | `{"error": "Validation Error", "message": "Message must contain 1-500 characters.", "code": "INVALID_MESSAGE"}` | ✅ PASS |
| 2 | `test_invalid_session_id_validation` | Session ID chứa ký tự cấm (@, #, !!!) | `{'user_message': 'Cho tôi hỏi về CPU RTX 4090', 'session_id': 'invalid@session#id!!!'}` | 422 | 422 | `{"error": "Validation Error", "message": "Session ID must use 1-64 letters, numbers, underscores, or hyphens.", "code": "INVALID_SESSION_ID"}` | ✅ PASS |
| 3 | `test_request_length_contract` | Tin nhắn vượt giới hạn public contract 500 ký tự | `501 characters` | 422 | 422 | `{"error": "Validation Error", "message": "Message must contain 1-500 characters.", "code": "INVALID_MESSAGE"}` | ✅ PASS |
| 4 | `test_valid_chat_request` | Gửi tin nhắn hợp lệ tới AI Bot (Bypass DB) | `{'user_message': 'Xin chào, bạn có thể giúp gì cho tôi?', 'session_id': 'test_valid_session'}` | 200 | 200 | `{"chatbot_reply": "Dạ em chào bạn!"}` | ✅ PASS |
| 5 | `test_eval_contract_uses_header_and_returns_contexts` | Eval key nằm trong header và response có contexts | `POST /chat/eval + X-Eval-Key` | 200 | 200 | `{"chatbot_reply": "answer", "contexts": ["context-1"]}` | ✅ PASS |
| 6 | `test_eval_rejects_missing_key_with_structured_error` | Eval endpoint từ chối request thiếu X-Eval-Key | `POST /chat/eval without X-Eval-Key` | 403 | 403 | `{"error": "Forbidden", "message": "Invalid evaluation key.", "code": "INVALID_EVAL_KEY"}` | ✅ PASS |
| 7 | `test_missing_auth_uses_public_error_contract` | Lỗi authentication dùng cùng ErrorResponse schema | `POST /chat without Authorization` | 401 | 401 | `{"error": "Authentication Error", "message": "Bearer token is required.", "code": "AUTH_REQUIRED"}` | ✅ PASS |
| 8 | `test_llm_generation_timeout_504` | Mô phỏng AI xử lý quá lâu | `{'user_message': 'Tư vấn cấu hình PC chi tiết', 'session_id': 'test_timeout_session'}` | 504 | 504 | `{"error": "Timeout Error", "message": "Xin lỗi, câu hỏi này hơi phức tạp nên Bot suy nghĩ lâu quá. Bạn có thể hỏi lại ngắn gọn hơn được không?", "code": "LLM_GENERATION_TIMEOUT"}` | ✅ PASS |
| 9 | `test_internal_server_error_500` | Mô phỏng lỗi hệ thống nội bộ (Internal Server Error) | `{'user_message': 'Tư vấn cấu hình PC chi tiết', 'session_id': 'test_500_session'}` | 500 | 500 | `{"error": "Internal Server Error", "message": "Đã xảy ra lỗi hệ thống. Vui lòng thử lại sau.", "code": "INTERNAL_SERVER_ERROR"}` | ✅ PASS |
| 10 | `test_different_users_may_share_session_id` | Session lock được định danh bằng user UID và session ID | `2 users / same session_id` | both accepted | both accepted | `{"replies": ["user_a", "user_b"], "keys": ["user_a:shared_session", "user_b:shared_session"]}` | ✅ PASS |
| 11 | `test_busy_session_returns_429` | Gửi request thứ hai khi session đang xử lý | `2 x POST /chat same session` | 429 | 429 | `{"same_session": {"error": "Too Many Requests", "message": "Bot đang xử lý câu hỏi trước trong phiên này, vui lòng đợi chút nhé!", "code": "SESSION_LOCKED"}, "other_session": {"chatbot_reply": "other_busy_session"}}` | ✅ PASS |
| 12 | `test_model_allows_two_parallel_requests_and_queues_third` | Hai request chạy song song, request thứ ba chờ slot | `3 sessions / 2 model slots` | max_active=2 | max_active=2 | `{"replies": ["parallel_0", "parallel_1", "parallel_2"], "third_queued": true}` | ✅ PASS |
| 13 | `test_model_queue_releases_after_TimeoutError` | Slot được nhả sau timeout/lỗi để request tiếp theo chạy | `TimeoutError` | 504, then success | 504, then success | `{"chatbot_reply": "recovered"}` | ✅ PASS |
| 14 | `test_model_queue_releases_after_RuntimeError` | Slot được nhả sau timeout/lỗi để request tiếp theo chạy | `RuntimeError` | 500, then success | 500, then success | `{"chatbot_reply": "recovered"}` | ✅ PASS |
| 15 | `test_processing_timeout_cancels_only_stuck_request` | Timeout chỉ hủy request treo, request song song vẫn hoàn tất | `1 stuck + 1 normal request` | 504 + success | 504 + success | `{"chatbot_reply": "normal completed"}` | ✅ PASS |
| 16 | `test_model_queue_returns_429_after_5_seconds` | Queue quá 5 giây trả 429 và nhả session slot | `model busy beyond queue timeout` | 429 | 429 | `{"error": "Too Many Requests", "message": "Bot đang có nhiều yêu cầu. Vui lòng thử lại sau 0.01 giây.", "code": "MODEL_QUEUE_TIMEOUT"}` | ✅ PASS |
| 17 | `test_openapi_documents_public_response_contracts` | OpenAPI mô tả response models và status codes công khai | `GET /openapi.json (in-process)` | schemas documented | schemas documented | `{"chat_statuses": ["200", "401", "403", "422", "429", "500", "503", "504"]}` | ✅ PASS |
| 18 | `test_delete_session_history` | Xóa lịch sử phiên hội thoại (Mock DB) | `/sessions/test_valid_session` | 200 | 200 | `{"status": "ok", "message": "Đã xóa lịch sử session 'test_valid_session'"}` | ✅ PASS |
