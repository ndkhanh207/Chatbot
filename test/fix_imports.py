import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from utils import get_auth_headers
import os
import re

TEST_DIR = r"d:\doan\Chatbot\test"

for filename in os.listdir(TEST_DIR):
    if not filename.endswith(".py") or filename == "utils.py" or filename == "test_master_suite.py":
        continue
        
    filepath = os.path.join(TEST_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if "from test.utils import get_auth_headers" in content:
        content = content.replace("from test.utils import get_auth_headers\n", "")
        # Insert the correct import after sys.path.insert if it exists, otherwise at top
        
        injection = "import sys\nimport os\nsys.path.insert(0, os.path.dirname(__file__))\nfrom utils import get_auth_headers\n"
        
        content = injection + content
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Fixed imports in {filepath}")
