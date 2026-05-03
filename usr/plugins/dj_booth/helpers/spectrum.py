"""Real-time spectrum analyzer. Background task taps icecast stream, computes 64-band FFT."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)

BANDS = 64


async def spectrum_loop(stream_url: str, on_update) -> None:
    """
    Spawn ffmpeg piping the icecast stream as raw PCM. Read 1024-sample chunks,
    compute FFT, bucket to 64 log-spaced bands, call on_update(list[float]).
    Cancellable via task.cancel().
    """
    try:
        import numpy as np
    except ImportError:
        log.warning("dj_booth: spectrum disabled — numpy not installed")
        return
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", stream_url,
        "-f", "f32le", "-ac", "1", "-ar", "22050", "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        sample_rate = 22050
        chunk_samples = 2048
        chunk_bytes = chunk_samples * 4  # float32
        # Log-spaced band edges from 30 Hz to nyquist
        edges = np.logspace(np.log10(30), np.log10(sample_rate / 2), BANDS + 1)
        freqs = np.fft.rfftfreq(chunk_samples, d=1.0 / sample_rate)
        band_indices = []
        for i in range(BANDS):
            mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
            band_indices.append(np.where(mask)[0])
        while True:
            data = await proc.stdout.read(chunk_bytes)
            if not data or len(data) < chunk_bytes:
                await asyncio.sleep(0.05)
                continue
            samples = np.frombuffer(data, dtype=np.float32)
            mag = np.abs(np.fft.rfft(samples * np.hanning(chunk_samples)))
            bands = []
            for idx in band_indices:
                if idx.size:
                    bands.append(float(mag[idx].mean()))
                else:
                    bands.append(0.0)
            peak = max(bands) or 1.0
            normalized = [min(1.0, b / peak) for b in bands]
            try:
                on_update(normalized)
            except Exception:
                pass
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("dj_booth: spectrum loop error")
    finally:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except Exception:
            pass
