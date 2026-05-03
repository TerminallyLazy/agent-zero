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
