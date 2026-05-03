import pytest
from usr.plugins.dj_booth.helpers.mic import MicCapture


def test_mic_capture_is_singleton():
    # Ensure clean slate
    MicCapture._instance = None
    a = MicCapture.get()
    b = MicCapture.get()
    assert a is b


def test_mic_capture_defaults():
    MicCapture._instance = None
    m = MicCapture.get()
    assert m.active is False
    assert m.volume == 0.8
    assert m.device_index == 0


def test_mic_list_devices_returns_empty():
    assert MicCapture.list_devices() == []


@pytest.mark.asyncio
async def test_mic_start_returns_false_and_stays_inactive():
    MicCapture._instance = None
    m = MicCapture.get()
    result = await m.start(device_index=2)
    assert result is False
    assert m.active is False
    assert m.device_index == 2


@pytest.mark.asyncio
async def test_mic_stop_is_safe_to_call():
    MicCapture._instance = None
    m = MicCapture.get()
    await m.stop()
    assert m.active is False


def test_mic_set_volume_clamps():
    MicCapture._instance = None
    m = MicCapture.get()
    m.set_volume(2.5)
    assert m.volume == 2.0
    m.set_volume(-1.0)
    assert m.volume == 0.0
    m.set_volume(0.5)
    assert m.volume == 0.5
