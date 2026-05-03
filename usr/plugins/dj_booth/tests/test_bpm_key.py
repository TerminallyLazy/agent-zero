import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_detect_bpm_async_dispatches_to_executor(monkeypatch):
    from usr.plugins.dj_booth.helpers import bpm_key
    monkeypatch.setattr(bpm_key, "_detect_bpm_sync", lambda p: 128.5)
    bpm = await bpm_key.detect_bpm("/x.mp3")
    assert bpm == 128.5


@pytest.mark.asyncio
async def test_detect_key_async_dispatches_to_executor(monkeypatch):
    from usr.plugins.dj_booth.helpers import bpm_key
    monkeypatch.setattr(bpm_key, "_detect_key_sync", lambda p: "C major")
    k = await bpm_key.detect_key("/x.mp3")
    assert k == "C major"


def test_bpm_sync_returns_zero_on_failure(monkeypatch):
    from usr.plugins.dj_booth.helpers import bpm_key
    # aubio import will fail in the test env — that's the point
    result = bpm_key._detect_bpm_sync("/nonexistent.mp3")
    assert result == 0.0


def test_key_sync_returns_empty_on_failure():
    from usr.plugins.dj_booth.helpers import bpm_key
    result = bpm_key._detect_key_sync("/nonexistent.mp3")
    assert result == ""
