from langchain_ollama import ChatOllama

from config.config import Config
from app.utils.model_utils import get_ollama_model

def get_llm() -> ChatOllama:
    return ChatOllama(
        model=get_ollama_model(),
        temperature=0,
        client_kwargs={"timeout": Config.OLLAMA_REQUEST_TIMEOUT},
        top_p=0.05,
        num_predict=256,
        repeat_penalty=1.2,
    )
