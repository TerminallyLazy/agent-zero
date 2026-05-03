import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_spectrum_loop_handles_numpy_missing(monkeypatch):
    from usr.plugins.dj_booth.helpers import spectrum
    # Force the import inside the function to fail
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **kw):
        if name == "numpy":
            raise ImportError("test-no-numpy")
        return real_import(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    called = []
    await spectrum.spectrum_loop("http://x", called.append)
    assert called == []  # bailed before calling on_update


@pytest.mark.asyncio
async def test_spectrum_loop_terminates_on_cancel():
    """Verify the loop responds to cancellation cleanly."""
    from usr.plugins.dj_booth.helpers import spectrum
    # Patch subprocess so we don't actually spawn ffmpeg
    fake_proc = MagicMock()
    fake_proc.stdout.read = AsyncMock(side_effect=asyncio.CancelledError)
    fake_proc.terminate = MagicMock()
    fake_proc.wait = AsyncMock(return_value=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake_proc)):
        task = asyncio.create_task(spectrum.spectrum_loop("http://x", lambda b: None))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    fake_proc.terminate.assert_called()
