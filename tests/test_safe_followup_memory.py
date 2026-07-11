from types import SimpleNamespace

from app.core.intent.history_context import build_history_context, extract_structured_state


def test_followup_state_ignores_ai_prose_and_uses_metadata():
    history = [
        SimpleNamespace(type="human", content="build pc 30 trieu choi game"),
        SimpleNamespace(
            type="ai",
            content="Trash prose says CPU Intel Core i3-9999 and GPU RTX 9090.",
            additional_kwargs={
                "build_id": "BUILD-08908",
                "last_suggested_cpu": "Intel Core i9-13900K",
                "last_suggested_gpu": "RTX 4070",
            },
        ),
    ]

    state = extract_structured_state(history)
    context = build_history_context(history)

    assert state["cpu"] == "Intel Core i9-13900K"
    assert state["gpu"] == "RTX 4070"
    assert "i3-9999" not in context
    assert "RTX 9090" not in context
    assert "AI:" not in context
