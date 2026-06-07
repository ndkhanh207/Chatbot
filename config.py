import os
from pathlib import Path
from typing import Optional


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


DOTENV_PATH = Path(__file__).parent / '.env'
_load_dotenv(DOTENV_PATH)


def _env(key: str, default: Optional[str] = None) -> str:
    return os.getenv(key, default or '')


EMBEDDING_MODEL = _env('EMBEDDING_MODEL', 'AITeamVN/Vietnamese_Embedding')
EMBEDDING_DEVICE = _env('EMBEDDING_DEVICE', 'cpu')
CHAT_MODEL = _env('CHAT_MODEL', _env('OLLAMA_MODEL', 'Vi-Qwen2-1.5B-RAG.Q3_K_L'))
VECTOR_DB_DIR = _env('VECTOR_DB_DIR', './chroma_db')


class Config:
    EMBEDDING_MODEL = EMBEDDING_MODEL
    EMBEDDING_DEVICE = EMBEDDING_DEVICE
    CHAT_MODEL = CHAT_MODEL
    VECTOR_DB_DIR = VECTOR_DB_DIR


__all__ = [
    'EMBEDDING_MODEL',
    'EMBEDDING_DEVICE',
    'CHAT_MODEL',
    'VECTOR_DB_DIR',
    'Config',
]
