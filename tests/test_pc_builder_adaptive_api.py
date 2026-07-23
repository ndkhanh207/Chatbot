import re

import pytest
import requests

from tests.utils import get_auth_headers
from fastapi.testclient import TestClient
from main import app
from app.catalog import ShopCatalog
from config.config import Config

app.state.catalog = ShopCatalog.load(Config.PC_STORE_DATA)
client = TestClient(app)

API_URL = "/chat"
SESSION_API_BASE = "/sessions"
BUILD_ID = re.compile(r"- Mã bộ:\s*([^\s]+)")


def _send(session_id: str, message: str) -> str:
    response = client.post(
        API_URL,
        json={"user_message": message, "session_id": session_id},
        headers=get_auth_headers(),
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("data", payload)["chatbot_reply"]


def _clear(session_id: str) -> None:
    response = client.delete(
        f"{SESSION_API_BASE}/{session_id}",
        headers=get_auth_headers(),
    )
    response.raise_for_status()


def _build_id(reply: str) -> str:
    match = BUILD_ID.search(reply)
    assert match, reply
    return match.group(1)


def _assert_build(reply: str) -> None:
    for token in ("- Mã bộ:", "- CPU:", "- GPU:", "- Mainboard:", "- Tổng cộng:"):
        assert token in reply


@pytest.mark.parametrize(
    ("label", "message"),
    [
        ("gaming", "build pc 30 triệu chơi game"),
        ("office", "build pc 30 triệu"),
    ],
)
def test_vague_purpose_clarifies(label: str, message: str) -> None:
    session_id = f"test_pc_adaptive_vague_{label}"
    _clear(session_id)
    reply = _send(session_id, message)
    assert BUILD_ID.search(reply) is None
    assert "?" in reply


@pytest.mark.parametrize(
    ("label", "message"),
    [
        ("gaming", "build PC 30 triệu để chơi Valorant 1080p 240 FPS"),
        ("office", "build PC 30 triệu để xử lý Excel lớn, Power Query và Power BI"),
        ("delegated", "build pc 30 triệu chơi game, đừng hỏi thêm và tự chọn giúp mình"),
    ],
)
def test_ready_purpose_selects_catalog_build(label: str, message: str) -> None:
    session_id = f"test_pc_adaptive_ready_{label}"
    _clear(session_id)
    _assert_build(_send(session_id, message))


def test_detailed_purpose_without_budget_selects() -> None:
    session_id = "test_pc_adaptive_missing_budget"
    _clear(session_id)
    assert _build_id(_send(session_id, "tư vấn PC để chơi Valorant 1080p 240 FPS"))


def test_negative_budget_is_rejected() -> None:
    session_id = "test_pc_adaptive_negative_budget"
    _clear(session_id)
    assert "âm" in _send(
        session_id, "build PC âm 30 triệu để chơi Valorant 1080p 240 FPS"
    ).casefold()


def test_vague_then_detailed_workload_selects() -> None:
    session_id = "test_pc_adaptive_followup_purpose"
    _clear(session_id)
    first = _send(session_id, "build pc 30 triệu chơi game")
    second = _send(session_id, "chơi game valorant nhẹ")
    assert BUILD_ID.search(first) is None
    assert "?" in first
    assert _build_id(second)


def test_detailed_workload_then_budget_selects() -> None:
    session_id = "test_pc_adaptive_followup_budget"
    _clear(session_id)
    first = _send(session_id, "tư vấn PC để chơi Valorant 1080p 240 FPS")
    second = _send(session_id, "ngân sách 30 triệu")
    assert _build_id(first)
    assert _build_id(second)


def test_budget_update_preserves_workload() -> None:
    session_id = "test_pc_adaptive_budget_update"
    _clear(session_id)
    first_id = _build_id(_send(session_id, "build PC 30 triệu để chơi Valorant 1080p 240 FPS"))
    updated = _send(session_id, "tăng ngân sách lên 35 triệu")
    assert _build_id(updated)
    assert "35" in updated or first_id in updated


def test_alternative_excludes_current_build() -> None:
    session_id = "test_pc_adaptive_alternative"
    _clear(session_id)
    first_id = _build_id(_send(session_id, "build PC 30 triệu để chơi Valorant 1080p 240 FPS"))
    alternative_id = _build_id(_send(session_id, "cho mình xem bộ khác"))
    assert alternative_id != first_id
