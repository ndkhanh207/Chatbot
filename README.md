<div align="center">
  <h1>🌟 AI PC Builder Chatbot API</h1>
  <p><strong>Hệ sinh thái API Chatbot tư vấn lắp ráp, kiểm tra tương thích linh kiện máy tính và phân tích thông số kỹ thuật tự động.</strong></p>
</div>

> [!NOTE]
> Được xây dựng trên nền tảng FastAPI, tích hợp mô hình ngôn ngữ lớn Ollama (Vi-Qwen 1.5B) và kho lưu trữ tri thức Vector Store (ChromaDB) / MySQL nhằm mang lại trải nghiệm tư vấn thông minh và chính xác.

## Tính năng nổi bật

- **Tích hợp Local LLM:** Sử dụng mô hình Vi-Qwen2-1.5B qua Ollama giúp trò chuyện và phản hồi tự nhiên bằng tiếng Việt.
- **RAG & Hybrid Search:** Sử dụng ChromaDB và mô hình nhúng tiếng Việt (HuggingFace) để trích xuất linh kiện cực chuẩn dựa trên ngữ cảnh người dùng.
- **Kiến trúc Service Layer:** Mã nguồn được phân tách chặt chẽ giữa logic điều hướng (routing), xác thực và nghiệp vụ cốt lõi.
- **Bảo mật Firebase Auth:** Xác thực các endpoint REST API qua token của Firebase.
- **Hệ thống Kiểm thử (Testing) toàn diện:** Bộ test Pytest tự động kiểm tra RESTful API, Knowledge Base, độ tương đồng Vector và kỹ năng phân loại ý định (intent classification).
- **Giới hạn tốc độ (Rate Limiting):** Tích hợp SlowAPI giúp ngăn chặn spam và lạm dụng API.

## Yêu cầu môi trường

- **Python:** 3.12 trở lên.
- **Cơ sở dữ liệu:** MySQL Server (chạy local hoặc remote).
- **Ollama:** Đã cài đặt và pull sẵn model `Vi-Qwen2-1.5B-RAG` (hoặc tương đương).
- **Firebase:** File `firebase-adminsdk.json` dùng để xác thực.

## Hướng dẫn Khởi chạy (Quick Start)

### 1. Cài đặt thư viện (Dependencies)

```bash
# Tạo và kích hoạt môi trường ảo (trên Windows PowerShell)
python -m venv .venv
& .\venv\Scripts\Activate.ps1

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### 2. Cấu hình biến môi trường (`.env`)

Tạo một file `.env` ở thư mục gốc của dự án với nội dung cấu hình sau:

```env
# AI Models
EMBEDDING_MODEL=AITeamVN/Vietnamese_Embedding
EMBEDDING_DEVICE=cuda
EMBEDDING_LOCAL_FILES_ONLY=True
CHAT_MODEL=Vi-Qwen2-1.5B-RAG.Q3_K_L
VECTOR_DB_DIR=./chroma_db
PC_STORE_DATA=data/dataset

# MySQL Database
MYSQL_USER=root
MYSQL_PASSWORD=mat_khau_cua_ban
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DB=chat_history

# Firebase
FIREBASE_CREDENTIALS_PATH=firebase-adminsdk.json
```

> [!IMPORTANT]
> Bắt buộc phải đặt file `firebase-adminsdk.json` thật của bạn vào thư mục gốc. Nếu thiếu file này, các API yêu cầu xác thực (`verify_firebase_token`) sẽ báo lỗi.

### 3. Chạy Server

```bash
# Khởi chạy server FastAPI qua Uvicorn
python -m uvicorn main:app
```

API sẽ chạy tại địa chỉ: `http://127.0.0.1:8000`.

Nếu cần expose API ra ngoài internet (ví dụ để gọi từ Frontend Flutter), bạn có thể dùng ngrok:
```bash
ngrok http 8000
```

## Đặc tả API (Endpoints)

| Endpoint | Method | Mô tả |
| :--- | :---: | :--- |
| `/chat` | `POST` | Gửi câu hỏi tới AI Chatbot, phân tích ý định và tra cứu RAG. Yêu cầu token Firebase. |
| `/sessions/{id}` | `DELETE` | Xóa sạch bộ nhớ đệm và lịch sử phiên hội thoại. |
| `/test-knowledge-base` | `GET` | Tra cứu trực tiếp kho tri thức linh kiện bằng Hybrid Search. |
| `/v1/embeddings` | `POST` | API tạo text embeddings dùng mô hình ngôn ngữ nội bộ. |

### Payload Mẫu (`POST /chat`)

```json
{
  "user_message": "Tư vấn cho mình cấu hình PC 30 triệu chơi game",
  "session_id": "session_gaming_30m"
}
```

> [!TIP]
> **Tài liệu API Tự động (Swagger UI & ReDoc):**
> Vì dự án sử dụng FastAPI, bạn có thể xem và test thử các API trực tiếp trên trình duyệt thông qua giao diện tương tác tự động. Sau khi chạy server, hãy truy cập:
> - **Swagger UI:** `http://127.0.0.1:8000/docs`
> - **ReDoc:** `http://127.0.0.1:8000/redoc`

## Kiến trúc Phân Tầng (Architecture)

Dự án tuân thủ nghiêm ngặt mô hình Service Layer Pattern:

- **`app/api/`**: Controllers (`chat.py`) và các trình xử lý logic nghiệp vụ (`chat_services.py`).
- **`app/core/`**: Xử lý orchestration với LLM (`chat_handler.py`), kịch bản Prompt và Trình tìm kiếm lai (`search_engine.py`).
- **`app/memory/`**: Quản lý trạng thái và lịch sử hội thoại trong MySQL.
- **`app/guard/`**: Phụ trách bảo mật (`firebase_auth.py`) và Rate Limiting (`security.py`).
- **`data/` & `chroma_db/`**: Chứa dữ liệu file CSV linh kiện và Vector database.

## Hệ thống Kiểm thử (Testing Ecosystem)

Hệ thống được trang bị bộ kiểm thử tích hợp chuyên sâu, giả lập các tình huống thực tế và các lỗi dị thường (như Timeout 504, Lỗi 500, lỗi Validation 400).

```bash
# Chạy toàn bộ Master Test Suite
pytest tests/test_master_suite.py -v -s

# Chạy kiểm thử API tích hợp
pytest tests/test_restful_chat_api.py -v
pytest tests/test_knowledge_base_api.py -v

# Chạy kiểm thử RAG và mức độ hiểu ngữ nghĩa
pytest tests/test_specification.py -v
pytest tests/test_compatibility.py -v
```

> [!TIP]
> Các file kiểm thử (`pytest`) đã được cấu hình chạy cô lập (isolated logic) để không làm ảnh hưởng đến bộ nhớ (VRAM/RAM) hay dữ liệu thật của Uvicorn Server đang chạy.