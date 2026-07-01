import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from utils import get_auth_headers
import pytest
import requests
import threading
import time

API_STREAM = "http://127.0.0.1:8000/chat/stream"
API_STOP_BASE = "http://127.0.0.1:8000/chat"

def test_chat_stream_and_stop():
    """Kiểm tra mô phỏng gọi streaming và gửi tín hiệu stop giữa chừng."""
    session_id = "test_stream_stop_session"
    payload = {
        "user_message": "Hãy kể tên và mô tả chi tiết 10 dòng CPU mạnh nhất hiện nay",
        "session_id": session_id
    }

    chunks = []
    stop_response = {}

    def run_stream():
        try:
            with requests.post(API_STREAM, json=payload, stream=True, timeout=10, headers=get_auth_headers()) as r:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        chunks.append(chunk.decode("utf-8", errors="replace"))
        except requests.exceptions.RequestException as e:
            print(f"[Stream exit/timeout]: {e}")

    # Start streaming in a background thread
    t = threading.Thread(target=run_stream)
    t.start()

    # Chờ 1 giây để server bắt đầu stream
    time.sleep(1.0)

    # Gửi tín hiệu stop
    stop_url = f"{API_STOP_BASE}/{session_id}/stop"
    try:
        res = requests.post(stop_url, timeout=5, headers=get_auth_headers())
        stop_response["status_code"] = res.status_code
        stop_response["json"] = res.json()
    except Exception as e:
        print(f"[Stop API error]: {e}")

    t.join(timeout=5)

    print(f"\n=== KẾT QUẢ KIỂM THỬ STREAM & STOP ===")
    print(f"Tổng số chunks nhận được trước khi ngắt: {len(chunks)}")
    print(f"Phản hồi từ Stop API: {stop_response}")

    assert stop_response.get("status_code") == 200, "API Stop phải trả về thành công 200"
    assert stop_response["json"].get("status") == "success", "Tín hiệu stop phải được ghi nhận success"
    assert len(chunks) > 0, "Phải nhận được ít nhất 1 chunk từ luồng streaming"
