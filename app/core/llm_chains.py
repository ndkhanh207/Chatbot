from langchain_ollama import ChatOllama
from langchain_core.runnables import RunnableSequence

from util.model_utils import get_ollama_model
from template.prompt_templates import (
    ADVISOR_TEMPLATE, COMPAT_CHECK_TEMPLATE, SUGGESTION_TEMPLATE, REFORMULATE_TEMPLATE
)

_reformulate_chain = None
_chain: RunnableSequence | None = None
_compat_check_chain = None
_suggestion_chain = None

def get_llm() -> ChatOllama:
    return ChatOllama(
        model=get_ollama_model(),
        temperature=0.1,
        request_timeout=30,
        top_p=0.1,
    )

def get_chain() -> RunnableSequence:
    global _chain
    if _chain is None:
        _chain = ADVISOR_TEMPLATE | get_llm()
    return _chain

def get_compat_check_chain() -> RunnableSequence:
    global _compat_check_chain
    if _compat_check_chain is None:
        _compat_check_chain = COMPAT_CHECK_TEMPLATE | get_llm()
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
            model=get_ollama_model(), temperature=0.1, request_timeout=30
        )
    return _reformulate_chain
