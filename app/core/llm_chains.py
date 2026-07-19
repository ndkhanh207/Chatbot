from langchain_ollama import ChatOllama
from langchain_core.runnables import RunnableSequence
from langchain_core.prompts import ChatPromptTemplate

from config.config import Config
from app.utils.model_utils import get_ollama_model
from app.templates.prompt_templates import (
    BASIC_SEARCH_TEMPLATE, COMPAT_CHECK_TEMPLATE, SUGGESTION_TEMPLATE, EMERGENCY_LIST_TEMPLATE
)

_reformulate_chain = None
_basic_search_chain: RunnableSequence | None = None
_compat_check_chain = None
_suggestion_chain = None
_emergency_chain     = None
_pc_build_qa_chain = None

def _get_strict_llm() -> ChatOllama:
    """LLM dùng riêng cho emergency — temperature=0 để tuyệt đối tuân lệnh."""
    return ChatOllama(
        model=get_ollama_model(),
        temperature=0,        # ← không sáng tạo, chỉ làm theo lệnh
        client_kwargs={"timeout": Config.OLLAMA_REQUEST_TIMEOUT},
        top_p=0.05,           # ← càng hẹp càng ít "phiêu"
        num_predict=256,
        repeat_penalty=1.3,   # ← tránh lặp câu hỏi vặn
    )

def get_llm() -> ChatOllama:
    return ChatOllama(
        model=get_ollama_model(),
        temperature=0,
        client_kwargs={"timeout": Config.OLLAMA_REQUEST_TIMEOUT},
        top_p=0.05,
        num_predict=256,
        repeat_penalty=1.2,
    )

def get_basic_search_chain() -> RunnableSequence:
    global _basic_search_chain
    if _basic_search_chain is None:
        _basic_search_chain = BASIC_SEARCH_TEMPLATE | ChatOllama(
            model=get_ollama_model(),
            temperature=0,
            client_kwargs={"timeout": Config.OLLAMA_REQUEST_TIMEOUT},
            top_p=0.05,
            num_predict=384,
            repeat_penalty=1.2,
        )
    return _basic_search_chain

def _get_compat_llm() -> ChatOllama:
    """LLM dùng riêng cho compatibility check — repeat_penalty thấp để cho phép copy text y nguyên."""
    return ChatOllama(
        model=get_ollama_model(),
        temperature=0,
        client_kwargs={"timeout": Config.OLLAMA_REQUEST_TIMEOUT},
        top_p=0.05,
        num_predict=256,
        repeat_penalty=1.05,  # ← Hạ repeat_penalty để LLM có thể lặp lại đúng nguyên văn cảnh báo
    )

def get_compat_check_chain() -> RunnableSequence:
    global _compat_check_chain
    if _compat_check_chain is None:
        _compat_check_chain = COMPAT_CHECK_TEMPLATE | _get_compat_llm()
    return _compat_check_chain

def get_suggestion_chain() -> RunnableSequence:
    global _suggestion_chain
    if _suggestion_chain is None:
        _suggestion_chain = SUGGESTION_TEMPLATE | get_llm()
    return _suggestion_chain


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

def get_pc_build_qa_chain() -> RunnableSequence:
    """Chain dùng riêng cho trả lời câu hỏi phụ về bộ PC đã gợi ý."""
    global _pc_build_qa_chain
    if _pc_build_qa_chain is None:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            ("human", "{user_message}")
        ])
        _pc_build_qa_chain = prompt | ChatOllama(
            model=get_ollama_model(), temperature=0.1,
            client_kwargs={"timeout": Config.OLLAMA_REQUEST_TIMEOUT}, num_predict=256
        )
    return _pc_build_qa_chain
