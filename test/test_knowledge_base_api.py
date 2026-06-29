import os
import sys
import json
import pytest
import requests

# Thêm đường dẫn gốc của project vào sys.path để tránh lỗi ModuleNotFoundError khi chạy lệnh pytest trực tiếp
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

API_KB = "http://127.0.0.1:8000/test-knowledge-base"
REPORT_FILE = "test/reports/report_knowledge_base_api.md"

_test_results = []

def _update_md_report():
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    total = len(_test_results)
    passed = sum(1 for r in _test_results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    md_content = f"""# 🧠 Báo Cáo Kiểm Thử Tích Hợp Knowledge Base API (`/test-knowledge-base`)

Kiểm thử độc lập chuyên sâu API tra cứu tìm kiếm lai (Hybrid Search) trong kho dữ liệu linh kiện máy tính của hệ thống AI Chatbot.

## 📊 Thống kê chung
- **Tổng số Test Cases:** {total}
- **Thành công (PASS):** {passed}
- **Thất bại (FAIL):** {failed}
- **Tỷ lệ thành công:** {pass_rate:.1f}%

## 📋 Chi tiết kết quả kiểm thử

| # | Tên Test Case | Mô tả tình huống | Input / Params | Expected Status | Actual Status | Response Body (JSON) | Kết quả |
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


def test_kb_search_valid_query():
    """Tình huống 1: Tìm kiếm từ khóa hợp lệ (VD: RTX 3080)."""
    params = {"q": "RTX 3080", "top_k": 3}
    resp_body = ""
    try:
        response = requests.get(API_KB, params=params, timeout=10)
        data = response.json()
        resp_body = json.dumps(data, ensure_ascii=False)
        passed = (response.status_code == 200)
        err = "None" if passed else f"Unexpected response: {data}"
        status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_kb_search_valid_query",
        "description": "Tra cứu linh kiện hợp lệ (RTX 3080) với top_k=3",
        "input": str(params),
        "expected_status": 200,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_kb_search_valid_query: {err}"


def test_kb_search_category_filter():
    """Tình huống 2: Tìm kiếm kết hợp bộ lọc danh mục (category=GPU)."""
    params = {"q": "RTX", "category": "GPU", "top_k": 2}
    resp_body = ""
    try:
        response = requests.get(API_KB, params=params, timeout=10)
        data = response.json()
        resp_body = json.dumps(data, ensure_ascii=False)
        passed = (response.status_code == 200)
        err = "None" if passed else f"Unexpected response: {data}"
        status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_kb_search_category_filter",
        "description": "Tra cứu kèm bộ lọc danh mục (category=GPU)",
        "input": str(params),
        "expected_status": 200,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_kb_search_category_filter: {err}"


def test_kb_search_empty_query():
    """Tình huống 3: Truy vấn không có tham số q -> Kiểm tra phản hồi mặc định."""
    params = {"top_k": 5}
    resp_body = ""
    try:
        response = requests.get(API_KB, params=params, timeout=10)
        data = response.json()
        resp_body = json.dumps(data, ensure_ascii=False)
        passed = (response.status_code == 200)
        err = "None" if passed else f"Unexpected response: {data}"
        status_code = response.status_code
    except Exception as e:
        passed, err, status_code = False, str(e), 0

    _test_results.append({
        "name": "test_kb_search_empty_query",
        "description": "Truy vấn không có từ khóa q (mặc định)",
        "input": str(params),
        "expected_status": 200,
        "actual_status": status_code,
        "response_body": resp_body,
        "passed": passed,
        "error": err
    })
    _update_md_report()
    assert passed, f"Lỗi test_kb_search_empty_query: {err}"
