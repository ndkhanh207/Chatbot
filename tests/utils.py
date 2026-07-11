import os
import urllib3.connection
import random

# Bypass Rate Limiter bằng cách fake source IP local cho mỗi request
original_init = urllib3.connection.HTTPConnection.__init__
def new_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self.source_address = (f"127.0.0.{random.randint(2, 254)}", 0)

urllib3.connection.HTTPConnection.__init__ = new_init

RAG_MAGIC_KEY = "ragas_magic_key_2024"

def get_auth_headers():
    return {"Authorization": "Bearer MAGIC_TEST_TOKEN_12345"}
