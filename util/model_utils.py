"""Utility functions for Ollama model selection.

These helpers were originally defined in ``main.py``.  They have been moved to a
separate module so that ``main.py`` stays focused on the FastAPI application
logic and the functions can be unit‑tested independently.
"""

import os
import ollama
from config import CHAT_MODEL


def _extract_model_name(model_entry):
    """Return a readable model name from a string or dict.

    The Ollama API may return a list where each element is either a plain string
    or a dictionary containing ``name`` or ``model`` keys.  This helper normalises
    the entry to a simple string.
    """
    if isinstance(model_entry, str):
        return model_entry
    if isinstance(model_entry, dict):
        return model_entry.get('name') or model_entry.get('model') or ''
    return str(model_entry)


def _list_available_ollama_models():
    """Query Ollama for the list of available models.

    Different versions of the ``ollama`` package expose the model list via
    ``list_models``, ``models`` or ``model.list``.  This function tries each
    variant and returns a list of model descriptors (or an empty list on error).
    """
    if hasattr(ollama, 'list_models'):
        try:
            model_list = ollama.list_models()
            if isinstance(model_list, dict) and 'models' in model_list:
                return model_list['models']
            return model_list
        except Exception:
            pass

    if hasattr(ollama, 'models'):
        try:
            return ollama.models()
        except Exception:
            pass

    if hasattr(ollama, 'model') and hasattr(ollama.model, 'list'):
        try:
            return ollama.model.list()
        except Exception:
            pass

    return []


def get_ollama_model():
    """Determine which Ollama model should be used for generation.

    Priority order:
    1. ``OLLAMA_MODEL`` environment variable.
    2. ``CHAT_MODEL`` from ``config.py``.
    3. The first model that contains ``qwen`` (preferring those with ``rag``).
    4. Fallback to the first available model.
    5. Hard‑coded default ``Vi-Qwen2-1.5B-RAG.Q3_K_L``.
    """
    env_model = os.getenv('OLLAMA_MODEL', '').strip()
    if env_model:
        return env_model

    if CHAT_MODEL:
        return CHAT_MODEL

    try:
        models = _list_available_ollama_models()
    except Exception:
        models = []

    model_names = [_extract_model_name(m) for m in models if _extract_model_name(m)]
    for name in model_names:
        low = name.lower()
        if 'qwen' in low and 'rag' in low:
            return name
        if 'qwen' in low:
            return name

    if model_names:
        return model_names[0]

    return 'Vi-Qwen2-1.5B-RAG.Q3_K_L'
