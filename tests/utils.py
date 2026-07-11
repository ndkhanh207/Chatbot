import os
import random

RAG_MAGIC_KEY = "ragas_magic_key_2024"

def get_auth_headers():
    # Sử dụng chuẩn X-Forwarded-For để test Rate Limit cục bộ an toàn.
    return {
        "Authorization": "Bearer MAGIC_TEST_TOKEN_12345",
        "X-Forwarded-For": f"127.0.0.{random.randint(2, 254)}"
    }
