import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from usr.plugins.dj_booth.tools.dj_tool import DjTool
from usr.plugins.dj_booth.helpers import state as _state


class _FakeAgent:
    def __init__(self):
        self.context = MagicMock()
        self.agent_name = "test"


def _make_tool(method, args=None):
    t = DjTool(
        agent=_FakeAgent(),
        name="dj_tool",
        method=method,
        args=args or {},
        message="",
        loop_data=None,
    )
    return t


@pytest.mark.asyncio
async def test_status_returns_state_summary():
    _state.reset_state()
    s = _state.get_state()
    s.is_running = True
    s.engine = "ffmpeg"
    s.listener_count = 4
    t = _make_tool("status")
    resp = await t.execute()
    assert "ffmpeg" in resp.message
    assert "4" in resp.message
    assert resp.break_loop is False


@pytest.mark.asyncio
async def test_search_library_returns_matches(monkeypatch):
    fake_lib = MagicMock()
    fake_lib.search.return_value = [
        MagicMock(title="X", artist="Y", path="/x.mp3", album="", format="mp3"),
    ]
    from usr.plugins.dj_booth.api import dj_control
    monkeypatch.setattr(dj_control, "_get_library", lambda: fake_lib)
    t = _make_tool("search_library", args={"query": "X"})
    resp = await t.execute()
    assert "X" in resp.message
    assert "Y" in resp.message


@pytest.mark.asyncio
async def test_queue_track_calls_lifecycle(monkeypatch):
    fake_queue = AsyncMock()
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "queue_track", fake_queue)
    t = _make_tool("queue_track", args={"path": "/a.mp3"})
    resp = await t.execute()
    fake_queue.assert_awaited_once_with("/a.mp3", "a")
    assert "queued" in resp.message.lower()


@pytest.mark.asyncio
async def test_skip_calls_lifecycle(monkeypatch):
    fake_skip = AsyncMock()
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "skip_current", fake_skip)
    t = _make_tool("skip")
    await t.execute()
    fake_skip.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_method_returns_error_message():
    t = _make_tool("nonsense")
    resp = await t.execute()
    assert "unknown" in resp.message.lower()
    assert resp.break_loop is False
