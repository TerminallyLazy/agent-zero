import asyncio
import pytest
from unittest.mock import patch, MagicMock
from usr.plugins.dj_booth.helpers.engine import (
    StreamEngine, FfmpegEngine, select_engine,
)


def test_select_engine_returns_liquidsoap_when_present():
    with patch("shutil.which", side_effect=lambda b: "/usr/bin/liquidsoap" if b == "liquidsoap" else None):
        eng = select_engine()
    assert eng.__class__.__name__ == "LiquidsoapEngine"


def test_select_engine_returns_ffmpeg_when_liquidsoap_absent():
    with patch("shutil.which", side_effect=lambda b: None if b == "liquidsoap" else "/usr/bin/ffmpeg"):
        eng = select_engine()
    assert eng.__class__.__name__ == "FfmpegEngine"


def test_select_engine_raises_when_neither_present():
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="neither liquidsoap nor ffmpeg"):
            select_engine()


@pytest.mark.asyncio
async def test_ffmpeg_engine_queue_and_skip():
    eng = FfmpegEngine()
    await eng.queue_track("/path/a.mp3")
    await eng.queue_track("/path/b.mp3")
    assert eng.queue.qsize() == 2
    await eng.clear_queue()
    assert eng.queue.qsize() == 0


@pytest.mark.asyncio
async def test_ffmpeg_engine_is_alive_before_start():
    eng = FfmpegEngine()
    assert await eng.is_alive() is False


from usr.plugins.dj_booth.helpers.engine import LiquidsoapEngine, render_liq_script


def test_render_liq_script_has_required_sections():
    cfg = {
        "icecast_port": 8000, "icecast_source_password": "pw",
        "stream_name": "n", "stream_description": "d", "stream_genre": "g",
        "stream_url": "u", "mount": "/stream", "bitrate": 192,
        "public_listing": False,
    }
    script = render_liq_script(cfg)
    assert 'set("server.telnet", true)' in script
    assert 'set("server.telnet.port", 1234)' in script
    assert 'request.queue(id="main")' in script
    assert "output.icecast" in script
    assert 'mount="/stream"' in script
    assert "%mp3(bitrate=192)" in script
    assert "mksafe" in script


@pytest.mark.asyncio
async def test_liquidsoap_engine_telnet_round_trip(monkeypatch):
    """Stub the telnet send to confirm command formatting."""
    eng = LiquidsoapEngine()
    sent = []

    async def fake_send(cmd: str) -> str:
        sent.append(cmd)
        if cmd.startswith("main.push"):
            return "1"
        if cmd == "request.on_air":
            return "1"
        if cmd.startswith("request.metadata"):
            return 'title="X"\nartist="Y"'
        return "OK"

    monkeypatch.setattr(eng, "_telnet_send", fake_send)

    await eng.queue_track("/m/a.mp3")
    assert sent[-1] == "main.push /m/a.mp3"

    await eng.skip()
    assert sent[-1] == "main.skip"

    current = await eng.get_current()
    assert current and "Y" in current and "X" in current
