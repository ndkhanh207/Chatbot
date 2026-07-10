# 🌟 AI PC Builder Chatbot - Backend & API Ecosystem

> **Hệ sinh thái API Chatbot tư vấn lắp ráp, kiểm tra tương thích linh kiện máy tính và phân tích thông số kỹ thuật tự động.** Được xây dựng trên nền tảng **FastAPI**, tích hợp mô hình ngôn ngữ lớn **Ollama (Vi-Qwen 1.5B)** và kho lưu trữ tri thức **Vector Store / MySQL** nhằm mang lại trải nghiệm tư vấn thông minh, chính xác tuyệt đối.

---

## 🏗️ Kiến Trúc Phân Tầng (Service Layer Pattern)

Dự án tuân thủ nghiêm ngặt mô hình kiến trúc phân tầng (Service Layer), đảm bảo việc tách biệt hoàn toàn giữa routing, xác thực dữ liệu và logic nghiệp vụ cốt lõi:

```text
📦 Chatbot
 ├── 📂 app
 │    ├── 📂 api
 │    │    ├── 📂 api_handler
 │    │    │    └── 📄 chat_services.py   # Business logic, quản lý thread pool, xử lý Timeout 504 & Lỗi 500
 │    │    ├── 📂 model
 │    │    │    └── 📄 chat_models.py     # Pydantic schemas (ChatRequest, ChatResponse, ErrorResponse)
 │    │    └── 📄 chat.py                 # Router / Controller điều hướng API
 │    ├── 📂 core
 │    │    ├── 📄 chat_handler.py         # Kết nối LangChain, Ollama LLM và RAG
 │    │    └── 📄 search_engine.py        # Trình tìm kiếm lai (Hybrid Search)
 │    ├── 📂 memory
 │    │    └── 📄 memory_store.py         # Quản lý phiên hội thoại (Session Store)
 │    └── 📂 utils
 │         └── 📄 unit_converter.py       # Bộ quy đổi thông số kỹ thuật (GB/MB, GHz/MHz)
 ├── 📂 test                              # Hệ thống kiểm thử tự động chuyên sâu (Pytest)
 │    ├── 📂 reports                      # Các file báo cáo kết quả kiểm thử tự động sinh (Markdown)
 │    ├── 📄 test_master_suite.py         # Trình quản lý chạy toàn bộ bộ kiểm thử (Master Runner)
 │    ├── 📄 test_restful_chat_api.py     # Module kiểm thử tích hợp RESTful Chat API
 │    ├── 📄 test_knowledge_base_api.py   # Module kiểm thử tích hợp Knowledge Base API
 │    ├── 📄 test_cosine_similarity.py    # Module kiểm thử độ tương đồng Cosine Similarity
 │    ├── 📄 test_pc_builder_api.py       # Module kiểm thử tư vấn PC Builder
 │    ├── 📄 test_specification.py        # Module kiểm thử nhận diện thông số
 │    ├── 📄 test_compatibility.py        # Module kiểm thử tương thích linh kiện
 │    └── 📄 test_price_check.py          # Module kiểm thử tra cứu giá
 └── 📄 main.py                           # Điểm khởi chạy ứng dụng & Cấu hình CORS Middleware
```

---

## 🚀 Hướng dẫn Cài đặt & Khởi chạy

### 1. Yêu cầu môi trường
* **Python:** 3.12+
* **Database:** MySQL Server
* **LLM Engine:** Ollama (đã pull model `Vi-Qwen`)

### 2. Kích hoạt môi trường & Bật Server
Trên Terminal (PowerShell / Bash), kích hoạt môi trường ảo và khởi chạy FastAPI server qua Uvicorn:

```bash
# Kích hoạt môi trường ảo (Windows PowerShell)
& .\venv\Scripts\Activate.ps1

# Khởi chạy server FastAPI (Mặc định: http://127.0.0.1:8000)
python -m uvicorn main:app
```

### 3. Expose API ra Internet (Dành cho Frontend Flutter)
Sử dụng Ngrok để forward cổng `8000` ra public URL với domain cố định:

```bash
ngrok http --url=<YOUR_URL_HERE> 8000
Ex:
ngrok http --url=customer-outskirts-blubber.ngrok-free.dev 8000
```

---

## 🔌 Đặc tả Giao thức API (RESTful Endpoints)

| Endpoint | HTTP Method | Mô tả & Công dụng chính | Payload / Params | Phản hồi Thành công | Các mã lỗi hỗ trợ |
| :--- | :---: | :--- | :--- | :--- | :--- |
| `/chat` | `POST` | Gửi câu hỏi tới AI Chatbot, phân tích ý định và tra cứu RAG | `{"user_message": "...", "session_id": "..."}` | `201 Created` kèm `chatbot_reply` | `400` (Validation), `500` (Server Error), `504` (Timeout) |
| `/sessions/{id}` | `DELETE` | Xóa sạch bộ nhớ đệm và lịch sử phiên hội thoại | Param `session_id` | `200 OK` | `500` (Server Error) |
| `/test-knowledge-base` | `GET` | Tra cứu trực tiếp kho tri thức linh kiện bằng Hybrid Search | `?q=RTX 3080&category=GPU&top_k=5` | `200 OK` (Danh sách linh kiện) | `500` (Server Error) |
| `/calculate` | `GET` | Quy đổi tự động đơn vị thông số (GB/MB, GHz/MHz) | `?value=64&from_unit=GB&to_unit=MB` | `200 OK` kèm `result` | `400` (Lỗi tham số) |

### Chi tiết Payload & Phản hồi mẫu (`POST /chat`)

**Request Payload:**
```json
{
  "user_message": "Tư vấn cho mình cấu hình PC 30 triệu chơi game",
  "session_id": "session_gaming_30m"
}
```

**Response Thành công (201 Created):**
```json
{
  "chatbot_reply": "Dạ, Dưới đây là danh sách các linh kiện gợi ý được cung cấp:\n[GPU] MSI GeForce RTX 3080 | Giá: 18.600.000 VNĐ..."
}
```

---

## 🛡️ Hệ thống Kiểm thử Tự động (Testing Ecosystem)

Hệ thống được trang bị bộ kiểm thử tích hợp chuyên sâu, giả lập 100% các tình huống thực tế và các lỗi dị thường (như Timeout 504, Internal Server Error 500, lỗi Validation 400).

### 1. Chạy toàn bộ kiểm thử (Master Test Suite)
Tính năng cách ly tiến trình tuyệt đối (Process Isolation) đảm bảo từng module chạy trong môi trường độc lập, tự động tổng hợp báo cáo:

```bash
python tests/test_master_suite.py
# HOẶC CHẠY QUA PYTEST
pytest tests/test_master_suite.py -v -s
```

### 2. Chạy từng module kiểm thử độc lập
Mỗi module tập trung vào một phân hệ nghiệp vụ cụ thể trong hệ thống:

```bash
# 1. Kiểm thử tích hợp RESTful Chat API (201, 400, 500, 504, Delete Session)
pytest tests/test_restful_chat_api.py -v -s

# 2. Kiểm thử tích hợp trực tiếp API tra cứu Knowledge Base (/test-knowledge-base)
pytest tests/test_knowledge_base_api.py -v -s

# 3. Kiểm thử chất lượng phản hồi tư vấn PC Builder (Single-turn)
python -m pytest tests/test_pc_builder_api.py -v

# 4. Kiểm thử chất lượng tư vấn PC Builder (Multi-turn - Nâng cấp, Khóa, Đổi linh kiện)
python -m pytest tests/test_pc_builder_multi_turn_api.py -v

# 5. Kiểm thử nhận diện và trích xuất thông số linh kiện
pytest tests/test_specification.py -v

# 6. Kiểm thử thuật toán kiểm tra tương thích linh kiện (Compatibility)
pytest tests/test_compatibility.py -v

# 7. Kiểm thử tra cứu độ tương đồng Cosine Similarity (Knowledge Base)
pytest tests/test_cosine_similarity.py -v

# 8. Kiểm thử chức năng tra cứu giá cả linh kiện
pytest tests/test_price_check.py -v

# 9. Kiểm tra hiểu ngữ nghĩa context
pytest tests/test_context_tracking_api.py -v
```
---
*Dự án tối ưu hóa dành riêng cho hệ thống Backend Chatbot AI và ứng dụng di động Flutter.*