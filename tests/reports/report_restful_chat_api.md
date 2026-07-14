# 🚀 Báo Cáo Kiểm Thử Tích Hợp RESTful Chat API (Có bảo mật Firebase Auth)

Kiểm thử REST API, Firebase Auth, validation, timeout, session lock, hàng đợi và giới hạn hai model request chạy song song.

## 📊 Thống kê chung
- **Tổng số Test Cases:** 12
- **Thành công (PASS):** 12
- **Thất bại (FAIL):** 0
- **Tỷ lệ thành công:** 100.0%

## 📋 Chi tiết kết quả kiểm thử

| # | Tên Test Case | Mô tả tình huống | Input / URL | Expected Status | Actual Status | Response Body (JSON) | Kết quả |
|---|---|---|---|---|---|---|---|
| 1 | `test_empty_message_validation` | Gửi tin nhắn rỗng (bị bỏ trống) | `{'user_message': '   ', 'session_id': 'test_session_1'}` | 400 | 400 | `{"error": "Validation Error", "message": "Nội dung tin nhắn không được để trống.", "code": "EMPTY_MESSAGE"}` | ✅ PASS |
| 2 | `test_invalid_session_id_validation` | Session ID chứa ký tự cấm (@, #, !!!) | `{'user_message': 'Cho tôi hỏi về CPU RTX 4090', 'session_id': 'invalid@session#id!!!'}` | 400 | 400 | `{"error": "Validation Error", "message": "Session không hợp lệ. Vui lòng thử lại ở phiên chat mới.", "code": "INVALID_SESSION_ID"}` | ✅ PASS |
| 3 | `test_valid_chat_request` | Gửi tin nhắn hợp lệ tới AI Bot (Bypass DB) | `{'user_message': 'Xin chào, bạn có thể giúp gì cho tôi?', 'session_id': 'test_valid_session'}` | 201/200 | 201 | `{"chatbot_reply": "Dạ em chào bạn!", "contexts": null}` | ✅ PASS |
| 4 | `test_llm_generation_timeout_504` | Mô phỏng AI xử lý quá lâu (Timeout - nay trả về 500) | `{'user_message': 'Tư vấn cấu hình PC chi tiết', 'session_id': 'test_timeout_session'}` | 500 | 500 | `Internal Server Error` | ✅ PASS |
| 5 | `test_internal_server_error_500` | Mô phỏng lỗi hệ thống nội bộ (Internal Server Error) | `{'user_message': 'Tư vấn cấu hình PC chi tiết', 'session_id': 'test_500_session'}` | 500 | 500 | `Internal Server Error` | ✅ PASS |
| 6 | `test_busy_session_returns_429` | Gửi request thứ hai khi session đang xử lý | `2 x POST /chat same session` | 429 | 429 | `{"same_session": {"error": "Too Many Requests", "message": "Bot đang xử lý câu hỏi trước trong phiên này, vui lòng đợi chút nhé!", "code": "SESSION_LOCKED"}, "other_session": {"chatbot_reply": "other_busy_session"}}` | ✅ PASS |
| 7 | `test_model_allows_two_parallel_requests_and_queues_third` | Hai request chạy song song, request thứ ba chờ slot | `3 sessions / 2 model slots` | max_active=2 | max_active=2 | `{"replies": ["parallel_0", "parallel_1", "parallel_2"], "third_queued": true}` | ✅ PASS |
| 8 | `test_model_queue_releases_after_TimeoutError` | Slot được nhả sau timeout/lỗi để request tiếp theo chạy | `TimeoutError` | 504, then success | 504, then success | `{"chatbot_reply": "recovered"}` | ✅ PASS |
| 9 | `test_model_queue_releases_after_RuntimeError` | Slot được nhả sau timeout/lỗi để request tiếp theo chạy | `RuntimeError` | 500, then success | 500, then success | `{"chatbot_reply": "recovered"}` | ✅ PASS |
| 10 | `test_processing_timeout_cancels_only_stuck_request` | Timeout chỉ hủy request treo, request song song vẫn hoàn tất | `1 stuck + 1 normal request` | 504 + success | 504 + success | `{"chatbot_reply": "normal completed"}` | ✅ PASS |
| 11 | `test_model_queue_returns_429_after_5_seconds` | Queue quá 5 giây trả 429 và nhả session slot | `model busy beyond queue timeout` | 429 | 429 | `{"error": "Too Many Requests", "message": "Bot đang có nhiều yêu cầu. Vui lòng thử lại sau 0.01 giây.", "code": "MODEL_QUEUE_TIMEOUT"}` | ✅ PASS |
| 12 | `test_delete_session_history` | Xóa lịch sử phiên hội thoại (Mock DB) | `/sessions/test_valid_session` | 200 | 200 | `{"status": "ok", "message": "Đã xóa lịch sử session 'test_valid_session'"}` | ✅ PASS |
