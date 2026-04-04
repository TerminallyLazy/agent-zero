from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from usr.plugins.chrome_extension.helpers import session_store


@pytest.fixture(autouse=True)
def _clear_session_store():
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


def test_session_store_command_lifecycle_round_trip() -> None:
    snapshot = session_store.upsert_session(
        "browser-1",
        active_tab_id=7,
        tabs=[
            {
                "tab_id": 7,
                "window_id": 1,
                "url": "https://example.com",
                "title": "Example",
                "active": True,
                "focused": True,
            }
        ],
        capabilities={"bridge": "mv3"},
    )
    assert snapshot["browser_session_id"] == "browser-1"
    assert snapshot["active_tab_id"] == 7

    command = session_store.enqueue_command(
        "browser-1",
        "inspect_dom",
        payload={"max_nodes": 5},
        target_tab_id=7,
        timeout_seconds=5,
    )
    assert command["status"] == "queued"

    pulled = session_store.pull_next_command("browser-1", redelivery_seconds=60)
    assert pulled is not None
    assert pulled["command_id"] == command["command_id"]
    assert pulled["status"] == "dispatched"
    assert pulled["attempts"] == 1

    completed = session_store.store_command_result(
        "browser-1",
        command["command_id"],
        status="completed",
        result={"nodes": [{"node_id": "body > button:nth-of-type(1)"}]},
        active_tab_id=7,
        tabs=[
            {
                "tab_id": 7,
                "window_id": 1,
                "url": "https://example.com",
                "title": "Example",
                "active": True,
                "focused": True,
            }
        ],
    )
    assert completed["status"] == "completed"
    assert completed["result"]["nodes"][0]["node_id"] == "body > button:nth-of-type(1)"

    session = session_store.get_session("browser-1")
    assert session is not None
    assert session["pending_commands"] == 0
    assert session["tabs"][0]["tab_id"] == 7


def test_wait_for_command_result_marks_timeout_as_failed() -> None:
    session_store.upsert_session("browser-timeout")
    command = session_store.enqueue_command(
        "browser-timeout",
        "scroll",
        payload={"direction": "down", "amount": 400},
        timeout_seconds=0.01,
    )

    result = asyncio.run(
        session_store.wait_for_command_result(
            "browser-timeout",
            command["command_id"],
            timeout_seconds=0.01,
            poll_interval=0.001,
        )
    )

    assert result["status"] == "failed"
    assert "Timed out" in result["error"]
