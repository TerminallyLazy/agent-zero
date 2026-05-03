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


@pytest.mark.asyncio
async def test_set_pitch_calls_lifecycle(monkeypatch):
    fake = AsyncMock()
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "set_pitch", fake)
    t = _make_tool("set_pitch", args={"deck": "b", "semitones": 2.5})
    resp = await t.execute()
    fake.assert_awaited_once_with("b", 2.5)
    assert "B" in resp.message
    assert "+2.50" in resp.message


@pytest.mark.asyncio
async def test_set_efx_calls_lifecycle(monkeypatch):
    fake = AsyncMock()
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "set_efx", fake)
    t = _make_tool("set_efx", args={"effect": "reverb", "param": "wet", "value": 0.4})
    resp = await t.execute()
    fake.assert_awaited_once_with("reverb", "wet", 0.4)
    assert "reverb" in resp.message


@pytest.mark.asyncio
async def test_set_efx_requires_effect_and_param():
    t = _make_tool("set_efx", args={"value": 0.5})
    resp = await t.execute()
    assert "requires" in resp.message.lower()


@pytest.mark.asyncio
async def test_announce_calls_lifecycle(monkeypatch):
    fake = AsyncMock()
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "announce", fake)
    t = _make_tool("announce", args={"text": "hello listeners"})
    resp = await t.execute()
    fake.assert_awaited_once_with("hello listeners")
    assert "hello listeners" in resp.message


@pytest.mark.asyncio
async def test_announce_rejects_empty_text(monkeypatch):
    fake = AsyncMock()
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "announce", fake)
    t = _make_tool("announce", args={"text": "   "})
    resp = await t.execute()
    fake.assert_not_called()
    assert "non-empty" in resp.message.lower()


@pytest.mark.asyncio
async def test_sync_bpm_computes_pitch_math(monkeypatch):
    """target_pitch_semitones = 12 * log2(src_bpm / tgt_bpm)."""
    src = MagicMock(bpm=140.0)
    tgt = MagicMock(bpm=120.0)
    fake_lib = MagicMock()
    fake_lib.get_track.side_effect = lambda p: src if p == "/src.mp3" else tgt
    from usr.plugins.dj_booth.api import dj_control
    monkeypatch.setattr(dj_control, "_get_library", lambda: fake_lib)

    captured = {}
    async def fake_pitch(deck, semitones):
        captured["deck"] = deck
        captured["semitones"] = semitones
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "set_pitch", fake_pitch)

    t = _make_tool("sync_bpm", args={
        "source_path": "/src.mp3",
        "target_path": "/tgt.mp3",
        "target_deck": "b",
    })
    resp = await t.execute()

    import math
    expected = 12.0 * math.log2(140.0 / 120.0)
    assert captured["deck"] == "b"
    assert abs(captured["semitones"] - expected) < 1e-9
    assert "140" in resp.message  # BPM mentioned in message


@pytest.mark.asyncio
async def test_sync_bpm_clamps_to_plus_minus_six(monkeypatch):
    """Big BPM ratio should clamp to ±6 semitones."""
    src = MagicMock(bpm=300.0)
    tgt = MagicMock(bpm=60.0)  # ratio 5 -> 12*log2(5) ≈ 27.86 st
    fake_lib = MagicMock()
    fake_lib.get_track.side_effect = lambda p: src if p == "/src.mp3" else tgt
    from usr.plugins.dj_booth.api import dj_control
    monkeypatch.setattr(dj_control, "_get_library", lambda: fake_lib)

    captured = {}
    async def fake_pitch(deck, semitones):
        captured["semitones"] = semitones
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "set_pitch", fake_pitch)

    t = _make_tool("sync_bpm", args={
        "source_path": "/src.mp3",
        "target_path": "/tgt.mp3",
    })
    await t.execute()
    assert captured["semitones"] == 6.0

    # And the negative direction
    src.bpm, tgt.bpm = 60.0, 300.0
    await t.execute()
    assert captured["semitones"] == -6.0


@pytest.mark.asyncio
async def test_sync_bpm_requires_analyzed_tracks(monkeypatch):
    src = MagicMock(bpm=0)
    tgt = MagicMock(bpm=120)
    fake_lib = MagicMock()
    fake_lib.get_track.side_effect = lambda p: src if p == "/src.mp3" else tgt
    from usr.plugins.dj_booth.api import dj_control
    monkeypatch.setattr(dj_control, "_get_library", lambda: fake_lib)

    fake = AsyncMock()
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "set_pitch", fake)

    t = _make_tool("sync_bpm", args={"source_path": "/src.mp3", "target_path": "/tgt.mp3"})
    resp = await t.execute()
    fake.assert_not_called()
    assert "analyzed" in resp.message.lower() or "bpm" in resp.message.lower()
