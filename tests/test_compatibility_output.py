import pytest

import app.compatibility.handler as handler_module
from app.chat.models import DomainRequest
from app.compatibility.compat_format import format_compatibility_reply
from app.compatibility.handler import CompatibilityHandler
from app.core.extraction.extractor import ExtractedEntities
from app.llm.result import LlmResult
from app.rag.models import GroundedAnswer


def test_compatibility_generation_validation_and_fallback():
    reply = format_compatibility_reply({
        "overall_status": "incompatible",
        "component_models": {"cpu": "Intel CPU", "mainboard": "AMD Main"},
        "cpu_main_check": {"cpu_socket": "LGA1700", "mainboard_socket": "AM5"},
        "gpu_main_check": None,
    })
    assert "không tương thích" in reply
    assert "LGA1700" in reply and "AM5" in reply


@pytest.mark.anyio
async def test_compatibility_handler_uses_valid_generation_and_rejects_contradiction(monkeypatch):
    components = {
        "CPU": {"product_id": "cpu", "name": "Intel CPU", "socket": "LGA1700"},
        "MAINBOARD": {"product_id": "main", "name": "AMD Main", "socket": "AM5"},
    }
    monkeypatch.setattr(
        handler_module,
        "resolve_component",
        lambda name, category, catalog: components.get(category),
    )

    generated = iter([
        GroundedAnswer(answer="Dạ, hai linh kiện tương thích.", grounded_status="compatible"),
        GroundedAnswer(answer="Dạ, hai linh kiện không tương thích do khác socket.", grounded_status="incompatible"),
    ])

    async def fake_generate(request):
        assert request.evidence.items[-1].facts["overall_status"] == "incompatible"
        return LlmResult(value=next(generated))

    monkeypatch.setattr(handler_module, "generate_grounded_answer", fake_generate)
    handler = CompatibilityHandler(catalog=object())
    request = DomainRequest(
        user_message="Intel CPU lắp với AMD Main được không?",
        user_uid="test",
        session_id="test",
    )
    intent = ExtractedEntities(
        intent="compatibility",
        cpu="Intel CPU",
        mainboard="AMD Main",
    )

    rejected = await handler.handle(request, intent)
    accepted = await handler.handle(request, intent)

    assert rejected.metadata["fallback"] is True
    assert "không tương thích" in rejected.reply
    assert accepted.metadata["fallback"] is False
    assert accepted.reply == "Dạ, hai linh kiện không tương thích do khác socket."
