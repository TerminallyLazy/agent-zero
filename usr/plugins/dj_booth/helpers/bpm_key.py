"""BPM + key detection. On-demand, runs in thread pool."""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


KEY_NAMES_MAJOR = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KEY_NAMES_MINOR = KEY_NAMES_MAJOR

# Krumhansl-Schmuckler profiles
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


async def detect_bpm(path: str) -> float:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _detect_bpm_sync, path)


async def detect_key(path: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _detect_key_sync, path)


def _detect_bpm_sync(path: str) -> float:
    try:
        import aubio
        import numpy as np
        win_s = 1024
        hop_s = 512
        src = aubio.source(path, 0, hop_s)
        sample_rate = src.samplerate
        tempo = aubio.tempo("default", win_s, hop_s, sample_rate)
        beats = []
        total = 0
        while True:
            samples, read = src()
            is_beat = tempo(samples)
            if is_beat:
                beats.append(tempo.get_last_s())
            total += read
            if read < hop_s:
                break
        if len(beats) < 4:
            return 0.0
        intervals = np.diff(beats)
        bpm = 60.0 / float(np.median(intervals))
        return round(bpm, 1)
    except Exception:
        log.exception("dj_booth: BPM detection failed for %s", path)
        return 0.0


def _detect_key_sync(path: str) -> str:
    try:
        import numpy as np
        # Decode to mono PCM via ffmpeg
        import subprocess
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", path, "-f", "f32le", "-ac", "1", "-ar", "22050", "-"],
            capture_output=True, timeout=120,
        )
        if proc.returncode != 0 or not proc.stdout:
            return ""
        pcm = np.frombuffer(proc.stdout, dtype=np.float32)
        if pcm.size < 22050:
            return ""
        # Compute chromagram via STFT magnitude binned to 12 pitch classes
        from scipy.signal import stft
        f, t, Z = stft(pcm, fs=22050, nperseg=4096, noverlap=2048)
        mag = np.abs(Z)
        # bin frequencies to MIDI notes mod 12
        midi = 69 + 12 * np.log2(np.maximum(f, 1e-6) / 440.0)
        pcs = np.mod(np.round(midi).astype(int), 12)
        chroma = np.zeros(12)
        for i in range(12):
            mask = pcs == i
            if mask.any():
                chroma[i] = mag[mask].mean()
        chroma = chroma / max(chroma.max(), 1e-9)
        # Score against profiles
        best_score = -1.0
        best = ""
        for shift in range(12):
            for profile, label_set, mode in (
                (MAJOR_PROFILE, KEY_NAMES_MAJOR, "major"),
                (MINOR_PROFILE, KEY_NAMES_MINOR, "minor"),
            ):
                shifted = np.roll(profile, shift)
                score = float(np.corrcoef(chroma, shifted)[0, 1])
                if np.isnan(score):
                    continue
                if score > best_score:
                    best_score = score
                    best = f"{label_set[shift]} {mode}"
        return best
    except Exception:
        log.exception("dj_booth: key detection failed for %s", path)
        return ""
