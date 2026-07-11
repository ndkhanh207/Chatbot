import asyncio

from app.core import health, llm_chains
from config.config import Config


def test_chat_client_has_real_http_timeout():
    llm = llm_chains.get_llm()

    assert llm.client_kwargs["timeout"] == Config.OLLAMA_REQUEST_TIMEOUT
    assert "request_timeout" not in llm.model_fields_set


def test_stuck_ollama_runner_is_killed(monkeypatch):
    killed = []

    class StuckClient:
        def __init__(self, timeout):
            assert timeout == 5

        async def generate(self, **kwargs):
            raise TimeoutError("stuck")

    monkeypatch.setattr(health.ollama, "AsyncClient", StuckClient)
    monkeypatch.setattr(health, "kill_ollama_runner", lambda: killed.append(True))

    asyncio.run(health.reset_ollama_model())

    assert killed == [True]
