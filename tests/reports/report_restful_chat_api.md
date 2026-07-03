# 🚀 Báo Cáo Kiểm Thử Tích Hợp RESTful Chat API (Có bảo mật Firebase Auth)

Kiểm thử toàn diện các tình huống thực tế (Thành công 201, Lỗi 400 Validation, Lỗi 500 System, Lỗi 504 Timeout, Delete Session) cho hệ thống AI Chatbot, có áp dụng Mock Firebase JWT.

## 📊 Thống kê chung
- **Tổng số Test Cases:** 6
- **Thành công (PASS):** 4
- **Thất bại (FAIL):** 2
- **Tỷ lệ thành công:** 66.7%

## 📋 Chi tiết kết quả kiểm thử

| # | Tên Test Case | Mô tả tình huống | Input / URL | Expected Status | Actual Status | Response Body (JSON) | Kết quả |
|---|---|---|---|---|---|---|---|
| 1 | `test_empty_message_validation` | Gửi tin nhắn rỗng (bị bỏ trống) | `{'user_message': '   ', 'session_id': 'test_session_1'}` | 400 | 400 | `{"error": "Validation Error", "message": "Nội dung tin nhắn không được để trống.", "code": "EMPTY_MESSAGE"}` | ✅ PASS |
| 2 | `test_invalid_session_id_validation` | Session ID chứa ký tự cấm (@, #, !!!) | `{'user_message': 'Cho tôi hỏi về CPU RTX 4090', 'session_id': 'invalid@session#id!!!'}` | 400 | 422 | `{"detail": [{"type": "string_pattern_mismatch", "loc": ["body", "session_id"], "msg": "String should match pattern '^[a-zA-Z0-9_-]+$'", "input": "invalid@session#id!!!", "ctx": {"pattern": "^[a-zA-Z0-9_-]+$"}}]}` | ✅ PASS |
| 3 | `test_valid_chat_request` | Gửi tin nhắn hợp lệ tới AI Bot (Bypass DB) | `{'user_message': 'Xin chào, bạn có thể giúp gì cho tôi?', 'session_id': 'test_valid_session'}` | 201/200 | 201 | `{"chatbot_reply": "Dạ em chào bạn!"}` | ✅ PASS |
| 4 | `test_llm_generation_timeout_504` | Mô phỏng AI xử lý quá lâu (Gateway Timeout) | `{'user_message': 'Tư vấn cấu hình PC chi tiết', 'session_id': 'test_timeout_session'}` | 504 | 0 | `` | ❌ FAIL<br>Chi tiết: `Expecting value: line 1 column 1 (char 0)` |
| 5 | `test_internal_server_error_500` | Mô phỏng lỗi hệ thống nội bộ (Internal Server Error) | `{'user_message': 'Tư vấn cấu hình PC chi tiết', 'session_id': 'test_500_session'}` | 500 | 0 | `` | ❌ FAIL<br>Chi tiết: `Expecting value: line 1 column 1 (char 0)` |
| 6 | `test_delete_session_history` | Xóa lịch sử phiên hội thoại (Mock DB) | `/sessions/test_valid_session` | 200 | 200 | `{"status": "ok", "message": "Đã xóa lịch sử session 'test_valid_session'"}` | ✅ PASS |
