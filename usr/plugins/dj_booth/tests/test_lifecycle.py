import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from usr.plugins.dj_booth.helpers import lifecycle, state


@pytest.mark.asyncio
async def test_start_stack_idempotent(monkeypatch):
    state.reset_state()
    s = state.get_state()
    s.is_running = True

    fake_ice = AsyncMock()
    fake_eng = AsyncMock()
    fake_eng.name = "ffmpeg"
    monkeypatch.setattr(lifecycle, "_get_icecast", lambda: fake_ice)
    monkeypatch.setattr(lifecycle, "_make_engine", lambda: fake_eng)

    await lifecycle.start_stack({"icecast_port": 8000})
    fake_ice.start.assert_not_called()


@pytest.mark.asyncio
async def test_start_stack_aborts_on_port_busy(monkeypatch):
    state.reset_state()

    def fake_bind_probe(port: int) -> None:
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(lifecycle, "_port_bind_probe", fake_bind_probe)

    with pytest.raises(RuntimeError, match="in use"):
        await lifecycle.start_stack({"icecast_port": 8000, "icecast_source_password": "x",
                                     "icecast_admin_password": "x", "music_dir": "/tmp"})

    s = state.get_state()
    assert s.is_running is False
    assert "in use" in s.error.lower()


@pytest.mark.asyncio
async def test_validate_config_required_fields():
    with pytest.raises(ValueError, match="icecast_port"):
        lifecycle.validate_config({})
    with pytest.raises(ValueError, match="icecast_source_password"):
        lifecycle.validate_config({"icecast_port": 8000})
    lifecycle.validate_config({
        "icecast_port": 8000, "icecast_source_password": "x",
        "icecast_admin_password": "x", "music_dir": "/tmp",
    })


@pytest.mark.asyncio
async def test_set_crossfader_clamps_and_writes_state(monkeypatch):
    state.reset_state()
    state.get_state().is_running = True
    fake_eng = AsyncMock()
    monkeypatch.setattr(lifecycle, "_engine", fake_eng)
    await lifecycle.set_crossfader(1.7)
    fake_eng.set_crossfader.assert_awaited_once()
    assert state.get_state().mixer.crossfader == 1.0
    await lifecycle.set_crossfader(-0.3)
    assert state.get_state().mixer.crossfader == 0.0


@pytest.mark.asyncio
async def test_queue_track_invalid_deck_raises(monkeypatch):
    state.reset_state()
    state.get_state().is_running = True
    monkeypatch.setattr(lifecycle, "_engine", AsyncMock())
    with pytest.raises(ValueError):
        await lifecycle.queue_track("/x.mp3", deck="c")


@pytest.mark.asyncio
async def test_set_pitch_clamps_and_writes_state(monkeypatch):
    state.reset_state()
    state.get_state().is_running = True
    fake_eng = AsyncMock()
    monkeypatch.setattr(lifecycle, "_engine", fake_eng)
    await lifecycle.set_pitch("a", 12.0)
    fake_eng.set_pitch.assert_awaited()
    assert state.get_state().deck_a.pitch == 6.0
    await lifecycle.set_pitch("b", -42.0)
    assert state.get_state().deck_b.pitch == -6.0


@pytest.mark.asyncio
async def test_set_pitch_invalid_deck_raises(monkeypatch):
    state.reset_state()
    state.get_state().is_running = True
    monkeypatch.setattr(lifecycle, "_engine", AsyncMock())
    with pytest.raises(ValueError):
        await lifecycle.set_pitch("c", 1.0)


@pytest.mark.asyncio
async def test_set_efx_writes_state(monkeypatch):
    state.reset_state()
    state.get_state().is_running = True
    fake_eng = AsyncMock()
    monkeypatch.setattr(lifecycle, "_engine", fake_eng)
    await lifecycle.set_efx("reverb", "wet", 0.4)
    assert state.get_state().efx.reverb_wet == 0.4
    await lifecycle.set_efx("filter", "freq", 1234.0)
    assert state.get_state().efx.filter_freq == 1234.0
    await lifecycle.set_efx("filter", "type", "highpass")
    assert state.get_state().efx.filter_type == "highpass"


@pytest.mark.asyncio
async def test_announce_skips_empty_text(monkeypatch):
    state.reset_state()
    state.get_state().is_running = True
    fake_eng = AsyncMock()
    monkeypatch.setattr(lifecycle, "_engine", fake_eng)
    await lifecycle.announce("   ")
    fake_eng.inject_tts.assert_not_called()
