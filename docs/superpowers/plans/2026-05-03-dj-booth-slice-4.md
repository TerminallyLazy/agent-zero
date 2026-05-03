# dj_booth Slice 4 Implementation Plan — Analysis (BPM, Key, Waveform, Spectrum)

> Use superpowers:subagent-driven-development.

**Goal:** Add per-track BPM + key detection, pre-computed waveform peaks for canvas rendering, and a real-time spectrum analyzer that drives the bar visualizer added in Slice 3.

**Architecture:** Three independent analysis surfaces, each in its own helper module with thread-pool execution to avoid blocking the asyncio loop:
1. `helpers/bpm_key.py` — `aubio` tempo for BPM, chromagram + Krumhansl-Schmuckler for key. On-demand only (user clicks Analyze, agent calls `analyze_track`).
2. Waveform pre-compute — added to `helpers/library.py`. When a track is queued/loaded onto a deck, generate a 1000-point peak array via ffmpeg-decoded raw PCM + numpy chunking. Cache on the Track dataclass.
3. `helpers/spectrum.py` — background asyncio task that taps the icecast stream, computes 64-band FFT every 100ms, writes to `StreamState.spectrum`. Liquidsoap engine has a side-output to a named pipe; ffmpeg engine taps the icecast HTTP source directly.

**Out of scope:**
- Liquidsoap script `!var` vs `{var}` syntax verification (Slice 3 polish — fix during real Docker integration)
- WebSocket spectrum push (MVP polls via existing status endpoint at 1Hz; visual interpolation done client-side)
- Beat-grid alignment, BPM sync (Slice 5)

---

## File changes

```
usr/plugins/dj_booth/
├── helpers/
│   ├── bpm_key.py        NEW — async wrappers + sync workers
│   ├── spectrum.py       NEW — background FFT loop
│   ├── library.py        MODIFY — Track gets bpm, key, waveform_peaks; add compute_waveform()
│   ├── state.py          MODIFY — StreamState.spectrum: list[float] (64 floats)
│   └── lifecycle.py      MODIFY — start/stop spectrum task; analyze on queue (optional)
├── api/
│   └── library.py        MODIFY — add 'analyze' action
├── webui/
│   ├── dj-store.js       MODIFY — analyzeTrack method; render waveform from peaks
│   └── dj-booth.html     MODIFY — waveform canvas (replace dummy bars); spectrum bars at top of mixer; show BPM/key on now-playing
├── hooks.py              MODIFY — install aubio, numpy, scipy
└── tests/
    ├── test_bpm_key.py   NEW
    ├── test_spectrum.py  NEW
    └── test_library.py   MODIFY — waveform tests
```

---

## Conventions

- **Thread pool**: `concurrent.futures.ThreadPoolExecutor(max_workers=2)` module-level. All sync workers run via `loop.run_in_executor`.
- **Spectrum format**: `list[float]` length 64, values 0..1 (normalized log magnitude).
- **Waveform format**: `list[float]` length 1000, values 0..1 (normalized peak per bucket).
- **Key string format**: `"C major"`, `"F# minor"`, etc. Empty `""` if undetected.

---

## Tasks

### Task 1: BPM + key detection (helpers/bpm_key.py)

**Files:** `helpers/bpm_key.py`, `tests/test_bpm_key.py`

Aubio + numpy/scipy heavy import — must lazy-import inside the worker functions so test collection doesn't trip the broken-numpy host env. Tests use monkeypatching, never call real aubio.

```python
# helpers/bpm_key.py
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
```

Tests:
```python
# tests/test_bpm_key.py
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
```

Commit: `feat(dj_booth): add BPM + key detection (Slice 4)`.

---

### Task 2: Waveform pre-compute on Track + LibraryManager

**Files:** `helpers/library.py`, `tests/test_library.py`

Add `bpm: float = 0.0`, `key: str = ""`, `waveform_peaks: list[float] = field(default_factory=list)` fields to `Track`.

Add `compute_waveform(path: str, bucket_count: int = 1000) -> list[float]` function that decodes audio with ffmpeg and chunks into max-amplitude buckets:

```python
def compute_waveform(path: str, bucket_count: int = 1000) -> list[float]:
    try:
        import subprocess
        import numpy as np
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", path, "-f", "f32le", "-ac", "1", "-ar", "8000", "-"],
            capture_output=True, timeout=60,
        )
        if proc.returncode != 0 or not proc.stdout:
            return []
        pcm = np.frombuffer(proc.stdout, dtype=np.float32)
        if pcm.size == 0:
            return []
        bucket_size = max(1, pcm.size // bucket_count)
        buckets = []
        for i in range(bucket_count):
            chunk = pcm[i * bucket_size:(i + 1) * bucket_size]
            if chunk.size:
                buckets.append(float(np.abs(chunk).max()))
            else:
                buckets.append(0.0)
        peak = max(buckets) or 1.0
        return [b / peak for b in buckets]
    except Exception:
        return []
```

Add `LibraryManager.analyze(path)` that calls all three (BPM + key + waveform) on a track, mutates the cached Track.

```python
async def analyze(self, path: str) -> Optional[Track]:
    t = self.get_track(path)
    if t is None:
        return None
    from usr.plugins.dj_booth.helpers import bpm_key
    import asyncio
    loop = asyncio.get_event_loop()
    t.bpm = await bpm_key.detect_bpm(path)
    t.key = await bpm_key.detect_key(path)
    t.waveform_peaks = await loop.run_in_executor(None, compute_waveform, path)
    return t
```

Tests (unit-level — monkey-patch ffmpeg + bpm_key):
```python
def test_compute_waveform_returns_empty_on_ffmpeg_failure(monkeypatch):
    from usr.plugins.dj_booth.helpers import library
    monkeypatch.setattr("subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 1, "stdout": b""})())
    assert library.compute_waveform("/x.mp3") == []


def test_track_has_analysis_fields():
    from usr.plugins.dj_booth.helpers.library import Track
    t = Track(path="/x.mp3")
    assert t.bpm == 0.0
    assert t.key == ""
    assert t.waveform_peaks == []


@pytest.mark.asyncio
async def test_library_analyze_populates_track(monkeypatch, tmp_path):
    from usr.plugins.dj_booth.helpers.library import LibraryManager, Track, AUDIO_EXTENSIONS
    from usr.plugins.dj_booth.helpers import bpm_key, library as lib_mod
    p = tmp_path / "x.mp3"
    p.write_bytes(b"\x00" * 1024)
    lib = LibraryManager()
    lib.scan(str(tmp_path))
    monkeypatch.setattr(bpm_key, "detect_bpm",
                        AsyncMock(return_value=120.0) if False else _async_const(120.0))
    monkeypatch.setattr(bpm_key, "detect_key", _async_const("C major"))
    monkeypatch.setattr(lib_mod, "compute_waveform", lambda path, bucket_count=1000: [0.5] * 1000)
    t = await lib.analyze(str(p))
    assert t is not None
    assert t.bpm == 120.0
    assert t.key == "C major"
    assert len(t.waveform_peaks) == 1000


def _async_const(val):
    async def _f(*a, **kw):
        return val
    return _f
```

(Note: `AsyncMock` needs `from unittest.mock import AsyncMock` at top of test_library.py if not already present.)

Commit: `feat(dj_booth): add waveform peaks + analyze on Track`.

---

### Task 3: Spectrum analyzer (helpers/spectrum.py)

**Files:** `helpers/spectrum.py`, `helpers/state.py`, `helpers/lifecycle.py`, `tests/test_spectrum.py`

Add `spectrum: list[float] = field(default_factory=list)` (64 floats) to `StreamState`. Reset to `[]` in `reset_state`.

```python
# helpers/spectrum.py
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
```

In `lifecycle.py`, add a `_spectrum_task` global. Spawn it after `_health_task` in `start_stack`; cancel it first in `stop_stack`. The callback writes to `state.get_state().spectrum`:

```python
_spectrum_task: Optional[asyncio.Task] = None

# In start_stack, after creating _health_task:
from usr.plugins.dj_booth.helpers.spectrum import spectrum_loop
def _on_spectrum(bands: list[float]):
    _state.get_state().spectrum = bands
_spectrum_task = asyncio.create_task(spectrum_loop(s.stream_url, _on_spectrum))

# In stop_stack, before _health_task cancel:
if _spectrum_task:
    _spectrum_task.cancel()
    try:
        await _spectrum_task
    except asyncio.CancelledError:
        pass
    _spectrum_task = None
_state.get_state().spectrum = []
```

Tests (mock ffmpeg pipe to feed canned bytes):
```python
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
```

(Note: import asyncio at top of the test file.)

Commit: `feat(dj_booth): add real-time spectrum analyzer`.

---

### Task 4: Library analyze API + tool

**Files:** `api/library.py`, `tools/dj_tool.py`

In `api/library.py`, add `analyze` action:
```python
elif action == "analyze":
    path = input.get("path", "")
    if not path:
        return {"error": "missing 'path'"}
    t = await lib.analyze(path)
    return {"track": asdict(t) if t else None}
```

In `tools/dj_tool.py`, add `analyze_track` sub-method:
```python
elif method == "analyze_track":
    from usr.plugins.dj_booth.api.dj_control import _get_library
    path = self.args.get("path", "")
    if not path:
        return Response(message="dj_tool: analyze_track requires 'path'", break_loop=False)
    t = await _get_library().analyze(path)
    if t is None:
        msg = f"track not found: {path}"
    else:
        msg = f"analyzed {t.title}: BPM={t.bpm}, key={t.key}, waveform={len(t.waveform_peaks)} peaks"
```

Update the unknown-method error string to include the new method.

Commit: `feat(dj_booth): add analyze API + dj_tool method`.

---

### Task 5: Frontend — render real waveforms + spectrum bars + BPM/key

**Files:** `webui/dj-store.js`, `webui/dj-booth.html`

Store: add `analyzeTrack(path)`. Add getters `spectrumBars` (returns `status?.spectrum || Array(64).fill(0)`).

```javascript
async analyzeTrack(path) {
    const data = await this._post(API_LIB, { action: "analyze", path });
    if (data && data.track) {
        toastFrontendSuccess(`Analyzed: BPM ${data.track.bpm}, key ${data.track.key}`, "DJ Booth");
        await this.fetchLibrary();
    }
},
get spectrumBars() {
    const s = this.status?.spectrum;
    if (!s || !s.length) return Array(64).fill(0);
    return s;
},
```

HTML: replace the dummy 32-bar deck waveforms with a `<canvas>` per deck that renders the now-playing track's `waveform_peaks` (read from the matched library track). Also add a 64-band spectrum bar row at the top of the mixer panel that reads from `$store.djBoothStore.spectrumBars`. Add a small BPM/key display next to each Now Playing.

For the deck waveform canvas, find the matching Track in `$store.djBoothStore.library.tracks` by `path === current_track`. If not found or `waveform_peaks` empty, fall back to flat bars.

Use a small Alpine `x-effect` block to redraw the canvas when state changes.

(Adapt cleanly — full HTML rewrite isn't required, just patch the deck waveform divs and add the spectrum row.)

```html
<!-- replace the existing .djb-waveform divs with: -->
<canvas class="djb-wave-canvas" width="400" height="40"
        x-ref="waveA" x-effect="$store.djBoothStore.drawWaveform($refs.waveA, 'a')"></canvas>
```

Add to the store:
```javascript
drawWaveform(canvas, deck) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);
    const ds = deck === "a" ? this.deckA : this.deckB;
    if (!ds.current_track) return;
    // Find matching track
    const track = (this.library.tracks || []).find(t => {
        const display = `${t.artist} - ${t.title}`.trim();
        return ds.current_track && (display === ds.current_track || ds.current_track.includes(t.title));
    });
    const peaks = track?.waveform_peaks || [];
    if (!peaks.length) {
        // flat fill
        ctx.fillStyle = deck === "a" ? "#00d4ff" : "#ff006e";
        ctx.globalAlpha = 0.3;
        ctx.fillRect(0, height/2 - 1, width, 2);
        return;
    }
    const bw = width / peaks.length;
    ctx.fillStyle = deck === "a" ? "#00d4ff" : "#ff006e";
    peaks.forEach((p, i) => {
        const h = Math.max(1, p * height);
        ctx.fillRect(i * bw, (height - h) / 2, Math.max(1, bw - 0.5), h);
    });
},
```

Add spectrum row in mixer panel:
```html
<div style="display: flex; gap: 1px; height: 30px; align-items: end; margin-bottom: 0.5rem;">
  <template x-for="(b, i) in $store.djBoothStore.spectrumBars" :key="i">
    <div :style="`flex:1; background: hsl(${200 + i*2}, 90%, 55%); height: ${Math.max(2, b*100)}%`"></div>
  </template>
</div>
```

Add BPM/key inline near Now Playing:
```html
<div style="font-size: 0.75rem; color: #aaa;" x-show="$store.djBoothStore.deckA.current_track">
  Use library Analyze to populate BPM/key
</div>
```

Library row: add an Analyze button per row (only if `bpm === 0`):
```html
<button class="djb-btn djb-lib-btn" x-show="!t.bpm"
        @click.stop="$store.djBoothStore.analyzeTrack(t.path)">⚡</button>
<span x-show="t.bpm" x-text="t.bpm.toFixed(0) + ' ' + (t.key || '')"
      style="font-size: 0.7rem; color: #ffbe0b;"></span>
```

Commit: `feat(dj_booth): real waveforms, spectrum bars, BPM/key display`.

---

### Task 6: Hooks — install analysis deps

Update `hooks.py:install()`:
```python
py_packages = [
    "mutagen>=1.47", "requests>=2.31",
    "aubio>=0.4.9", "numpy>=1.24", "scipy>=1.11",
]
apt_packages = ["icecast2", "liquidsoap", "ffmpeg", "libaubio-dev", "libsndfile1"]
```

Commit: `feat(dj_booth): install analysis deps in hooks (Slice 4)`.

---

### Task 7: Close-out

```bash
cd /Users/lazy/Desktop/agent-zero
python -m pytest usr/plugins/dj_booth/tests/ -v
git tag -a dj_booth/slice-4-complete -m "dj_booth Slice 4: BPM, key, waveform, spectrum"
```

Update README "Status" to reflect Slice 4 features. Commit + done.
