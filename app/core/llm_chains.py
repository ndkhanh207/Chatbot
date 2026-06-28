from langchain_ollama import ChatOllama
from langchain_core.runnables import RunnableSequence

from app.utils.model_utils import get_ollama_model
from app.templates.prompt_templates import (
    BASIC_SEARCH_TEMPLATE, COMPAT_CHECK_TEMPLATE, SUGGESTION_TEMPLATE, REFORMULATE_TEMPLATE, EMERGENCY_LIST_TEMPLATE,
)

_reformulate_chain = None
_basic_search_chain: RunnableSequence | None = None
_compat_check_chain = None
_suggestion_chain = None
_emergency_chain     = None  


def _get_strict_llm() -> ChatOllama:
    """LLM dùng riêng cho emergency — temperature=0 để tuyệt đối tuân lệnh."""
    return ChatOllama(
        model=get_ollama_model(),
        temperature=0,        # ← không sáng tạo, chỉ làm theo lệnh
        request_timeout=90,
        top_p=0.05,           # ← càng hẹp càng ít "phiêu"
        repeat_penalty=1.3,   # ← tránh lặp câu hỏi vặn
    )

def get_llm() -> ChatOllama:
    return ChatOllama(
        model=get_ollama_model(),
        temperature=0.1,
        request_timeout=90,
        top_p=0.1,
        num_predict=300,
        # repeat_penalty=1.2,
    )

def get_basic_search_chain() -> RunnableSequence:
    global _basic_search_chain
    if _basic_search_chain is None:
        _basic_search_chain = BASIC_SEARCH_TEMPLATE | get_llm()
    return _basic_search_chain

def get_compat_check_chain() -> RunnableSequence:
    global _compat_check_chain
    if _compat_check_chain is None:
        _compat_check_chain = COMPAT_CHECK_TEMPLATE | _get_strict_llm()
    return _compat_check_chain

def get_suggestion_chain() -> RunnableSequence:
    global _suggestion_chain
    if _suggestion_chain is None:
        _suggestion_chain = SUGGESTION_TEMPLATE | get_llm()
    return _suggestion_chain

def get_reformulate_chain():
    global _reformulate_chain
    if _reformulate_chain is None:
        _reformulate_chain = REFORMULATE_TEMPLATE | ChatOllama(
            model=get_ollama_model(), temperature=0.1,
        )
    return _reformulate_chain


def get_emergency_chain() -> RunnableSequence:
    """
    Chain dùng khi LLM bỏ qua rule và hỏi vặn lại khách.
    Dùng strict LLM (temperature=0) + EMERGENCY_LIST_TEMPLATE cứng hơn.
    KHÔNG cache — mỗi lần gọi là fresh instance để tránh state cũ.
    """
    global _emergency_chain
    if _emergency_chain is None:
        _emergency_chain = EMERGENCY_LIST_TEMPLATE | _get_strict_llm()
    return _emergency_chain