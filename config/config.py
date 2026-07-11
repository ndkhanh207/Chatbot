import os
# Tối ưu hóa bộ nhớ PyTorch cho GPU 4GB VRAM: ĐẶT TRƯỚC KHI IMPORT TORCH ĐỂ CÓ TÁC DỤNG
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True,garbage_collection_threshold:0.8,max_split_size_mb:128"
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "10")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "10")

from pathlib import Path
from typing import Optional

import torch
def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for line in dotenv_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        if '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


DOTENV_PATH = Path(__file__).parent.parent / '.env'
_load_dotenv(DOTENV_PATH)


def _env(key: str, default: Optional[str] = None) -> str:
    return os.getenv(key, default or '')


def _default_device() -> str:
    return 'cuda' if torch.cuda.is_available() else 'cpu'


EMBEDDING_MODEL = _env('EMBEDDING_MODEL', 'AITeamVN/Vietnamese_Embedding')
EMBEDDING_DEVICE = _env('EMBEDDING_DEVICE', '') or _default_device()
EMBEDDING_LOCAL_FILES_ONLY = _env('EMBEDDING_LOCAL_FILES_ONLY') != '0'
CHAT_MODEL = _env('CHAT_MODEL', _env('OLLAMA_MODEL', 'Vi-Qwen2-1.5B-RAG.Q3_K_L'))
OLLAMA_REQUEST_TIMEOUT = float(_env('OLLAMA_REQUEST_TIMEOUT', '45'))
VECTOR_DB_DIR = _env('VECTOR_DB_DIR', './chroma_db')
#MYSQL
MYSQL_USER     = _env('MYSQL_USER',     'root')
MYSQL_PASSWORD = _env('MYSQL_PASSWORD', '')
MYSQL_HOST     = _env('MYSQL_HOST',     '127.0.0.1')
MYSQL_PORT     = _env('MYSQL_PORT',     '3306')
MYSQL_DB       = _env('MYSQL_DB',       'chat_history')
MYSQL_TABLE    = _env('MYSQL_TABLE',    'chat_history')

# Base directory for data files
PC_STORE_DATA = _env('PC_STORE_DATA','data/dataset')


MYSQL_CONNECTION_STRING = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
)

class Config:
    EMBEDDING_MODEL = EMBEDDING_MODEL
    EMBEDDING_DEVICE = EMBEDDING_DEVICE
    EMBEDDING_LOCAL_FILES_ONLY = EMBEDDING_LOCAL_FILES_ONLY
    CHAT_MODEL = CHAT_MODEL
    OLLAMA_REQUEST_TIMEOUT = OLLAMA_REQUEST_TIMEOUT
    VECTOR_DB_DIR = VECTOR_DB_DIR
    MYSQL_CONNECTION_STRING = MYSQL_CONNECTION_STRING
    PC_STORE_DATA = PC_STORE_DATA
    MYSQL_HOST = MYSQL_HOST
    MYSQL_PORT = MYSQL_PORT
    MYSQL_USER = MYSQL_USER
    MYSQL_PASSWORD = MYSQL_PASSWORD
    MYSQL_DB = MYSQL_DB
    FIREBASE_CREDENTIALS_PATH = _env('FIREBASE_CREDENTIALS_PATH', 'firebase-adminsdk.json')

all = [
    'EMBEDDING_MODEL',
    'EMBEDDING_DEVICE',
    'CHAT_MODEL',
    'VECTOR_DB_DIR',
    'MYSQL_CONNECTION_STRING',
    'PC_STORE_DATA',
    'Config',
]
