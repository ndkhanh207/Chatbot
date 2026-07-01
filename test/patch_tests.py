import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from utils import get_auth_headers
import os
import re

TEST_DIR = r"d:\doan\Chatbot\test"

def patch_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    if "get_auth_headers" not in content:
        content = "from test.utils import get_auth_headers\n" + content
    
    # Replace requests.post/get/delete
    content = re.sub(
        r'(requests\.(?:post|get|delete|put)\([^)]+)',
        lambda m: m.group(1) if "headers=" in m.group(1) else m.group(1) + ", headers=get_auth_headers()",
        content
    )
    
    # Replace client.post/get/delete
    content = re.sub(
        r'(client\.(?:post|get|delete|put)\([^)]+)',
        lambda m: m.group(1) if "headers=" in m.group(1) else m.group(1) + ", headers=get_auth_headers()",
        content
    )
    
    # Remove mock of verify_firebase_token in test_restful_chat_api
    if "test_restful_chat_api.py" in filepath:
        content = re.sub(
            r'# Mock Firebase Auth Dependency.*?\n(?:def mock_verify_firebase_token.*?\n(?:    .*?\n)*)?mock_app\.dependency_overrides\[verify_firebase_token\] = mock_verify_firebase_token\n',
            '',
            content,
            flags=re.DOTALL
        )
        content = re.sub(r'from app\.api\.auth\.firebase_auth import verify_firebase_token\n', '', content)

    # Patch the incorrect mock path in test_restful_chat_api.py
    content = content.replace(
        '"app.api.api_handler.chat_services.handle_chat"',
        '"app.api.chat.handle_chat"'
    )

    if content != original_content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Patched {filepath}")

for filename in os.listdir(TEST_DIR):
    if filename.endswith(".py") and filename.startswith("test_") and filename != "test_master_suite.py":
        patch_file(os.path.join(TEST_DIR, filename))
