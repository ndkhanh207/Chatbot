from types import SimpleNamespace

from app.core.intent.history_context import build_history_context, extract_structured_state
from app.memory import memory_store
from app.memory.context_manager import ConversationContext
from app.pc_builder.context import PcBuildContext


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


def test_context_snapshot_isolated_by_user_uid(monkeypatch):
    shared_session_id = "shared_session"
    snapshots = {
        ("user_a", shared_session_id): [{"build_id": "BUILD-A"}],
        ("user_b", shared_session_id): [{"build_id": "BUILD-B"}],
    }
    monkeypatch.setattr(
        memory_store,
        "get_recent_metadata",
        lambda user_uid, session_id: snapshots[(user_uid, session_id)],
    )

    user_a = ConversationContext("user_a", shared_session_id).load_snapshot(PcBuildContext)
    user_b = ConversationContext("user_b", shared_session_id).load_snapshot(PcBuildContext)

    assert user_a.build_id == "BUILD-A"
    assert user_b.build_id == "BUILD-B"


def test_snapshot_loader_skips_newer_unrelated_intent(monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "get_recent_metadata",
        lambda *_: [
            {"intent": "price_check", "target_product": "rtx 4090"},
            {"build_id": "BUILD-42", "budget": 30_000_000},
        ],
    )

    snapshot = ConversationContext("user", "session").load_snapshot(PcBuildContext)

    assert snapshot.build_id == "BUILD-42"
    assert snapshot.budget == 30_000_000


def test_structured_state_uses_latest_snapshot_without_mixing_turns():
    history = [
        SimpleNamespace(
            type="ai",
            content="old",
            additional_kwargs={"intent": "price_check", "gpu": "rtx 4090"},
        ),
        SimpleNamespace(type="human", content="i7 14700k giá bao nhiêu"),
        SimpleNamespace(
            type="ai",
            content="new",
            additional_kwargs={"intent": "price_check", "cpu": "i7 14700k"},
        ),
    ]

    state = extract_structured_state(history)

    assert state["cpu"] == "i7 14700k"
    assert "gpu" not in state


def test_context_commit_writes_one_versioned_state_shape(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        memory_store,
        "save_message",
        lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs),
    )

    ConversationContext("user", "session").commit(
        "question",
        "answer",
        {"intent_state": {"intent": "price_check", "gpu": "rtx 4090"}},
    )

    assert captured["kwargs"]["metadata"] == {
        "context_version": 1,
        "state": {"intent": "price_check", "gpu": "rtx 4090"},
    }
