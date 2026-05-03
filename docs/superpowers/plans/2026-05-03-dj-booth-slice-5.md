# dj_booth Slice 5 Implementation Plan — Performance Features

> Use superpowers:subagent-driven-development.

**Goal:** Round out the DJ booth with the remaining performance-critical features from the parent spec: EFX rack (reverb, delay, filter), per-deck pitch + BPM sync, TTS announcements, mic input stub.

**Scope (in)**:
1. EFX rack — reverb wet, delay wet+time, filter freq+type. Server-controlled `interactive.float` refs in liquidsoap. Frontend knobs.
2. Pitch shift per deck (-6 to +6 semitones). Server-controlled. ffmpeg fallback ignores.
3. BPM sync — `dj_tool:sync_bpm source target` adjusts target deck's pitch ratio so its BPM matches source.
4. TTS announcements — `dj_tool:announce text` generates WAV via existing A0 speech helper, injects to liquidsoap via `tts.push <path>`.
5. Mic capture stub — `helpers/mic.py` with start/stop/list_devices interface; full PyAudio capture + named pipe wiring deferred ("Slice 5.5 polish") because it requires host audio hardware that's hard to test.

**Scope (out — explicitly deferred)**:
- Cue points (UI-only state, no engine integration)
- Loop regions (UI-only)
- Scratch on vinyl drag (needs SVG turntable, polish slice)
- Auto-DJ scheduler (own slice — pairs with `_task_scheduler` plugin)
- Slice 3 liquidsoap script syntax verification (still needs real Docker integration test)

**Spec ref:** `BUILD_DOCS/A0-SHOUTCAST-SPEC.md` "EFX Rack", "Microphone Section", "Transport Controls", "BPM/Key Display".

---

## File changes

```
usr/plugins/dj_booth/
├── helpers/
│   ├── state.py        MODIFY — DeckState.pitch, EFXState dataclass on StreamState
│   ├── engine.py       MODIFY — set_pitch, set_efx, inject_tts methods + liq script EFX section
│   ├── lifecycle.py    MODIFY — set_pitch/set_efx/announce wrappers
│   ├── mic.py          NEW — stub
│   └── tts.py          NEW — wraps A0 speech to WAV file, returns path
├── api/
│   └── dj_control.py   MODIFY — new actions
├── tools/
│   └── dj_tool.py      MODIFY — sync_bpm, announce, set_pitch, set_efx sub-methods
├── webui/
│   ├── dj-store.js     MODIFY — methods + getters
│   └── dj-booth.html   MODIFY — EFX rack + pitch slider per deck
├── hooks.py            MODIFY — pyaudio (best-effort)
└── tests/
    ├── test_state.py   MODIFY — EFXState defaults
    ├── test_engine.py  MODIFY — pitch, EFX, TTS routing
    ├── test_lifecycle.py MODIFY — clamping for new fields
    ├── test_dj_tool.py MODIFY — sync_bpm computation, announce dispatch
    └── test_mic.py     NEW — stub interface
```

---

## Conventions

- Pitch shift: stored as semitones (-6 to +6). Liquidsoap uses rate ratio `2 ** (semitones/12)`. Engine accepts semitones; conversion done internally.
- EFX wet ranges 0..1. Filter freq 20..20000 Hz (log scale frontend, linear backend). Filter type: `"lowpass" | "highpass" | "bandpass"`.
- BPM sync: target_pitch_semitones = `12 * log2(source_bpm / target_bpm)`. Clamped to ±6.
- TTS: file written to `/tmp/dj_booth_tts/<uuid>.wav`. Liquidsoap `tts` queue is a fallback source (already in spec §"liquidsoap script").

---

## Tasks

### Task 1: State — pitch + EFXState

**Files:** `helpers/state.py`, `tests/test_state.py`

Add `pitch: float = 0.0` to `DeckState`. Add new `EFXState`:
```python
@dataclass
class EFXState:
    reverb_wet: float = 0.0
    delay_wet: float = 0.0
    delay_time: float = 0.3
    filter_freq: float = 20000.0
    filter_type: str = "lowpass"  # lowpass | highpass | bandpass
```

Add `efx: EFXState = field(default_factory=EFXState)` to `StreamState`.

Tests: `test_efx_state_defaults`, `test_deck_state_has_pitch`, `test_reset_state_resets_efx`.

Commit: `feat(dj_booth): add EFXState + deck pitch (Slice 5)`.

---

### Task 2: Engine — pitch, EFX, TTS injection

**Files:** `helpers/engine.py`, `tests/test_engine.py`

Append to `LIQ_SCRIPT_TEMPLATE` after the EQ section but before the final `add` mix:

```
# Pitch (rate-based) per deck
pitch_a = interactive.float("deck_a.pitch", 1.0)
pitch_b = interactive.float("deck_b.pitch", 1.0)
deck_a = stretch(ratio=!pitch_a, deck_a)
deck_b = stretch(ratio=!pitch_b, deck_b)
```

After the master mix, add EFX chain:
```
# EFX
reverb_wet = interactive.float("efx.reverb_wet", 0.0)
delay_wet  = interactive.float("efx.delay_wet", 0.0)
delay_time = interactive.float("efx.delay_time", 0.3)
filter_freq = interactive.float("efx.filter_freq", 20000.0)
mix = ladspa.plate_2x2(mix, dry=!reverb_wet, wet=!reverb_wet)
mix = echo(delay=!delay_time, feedback=0.4, ping_pong=false, mix)
mix = filter.iir.butter.low(frequency=!filter_freq, mix)
```

Add TTS injection queue at the end (before `output.icecast`):
```
tts_queue = request.queue(id="tts")
mix = fallback(track_sensitive=false, [tts_queue, mix])
```

Add `LiquidsoapEngine` methods:
```python
async def set_pitch(self, deck: str, semitones: float) -> None:
    s = max(-6.0, min(6.0, float(semitones)))
    ratio = 2.0 ** (s / 12.0)
    target = "deck_a" if deck == "a" else "deck_b"
    await self._telnet_send(f"{target}.pitch.set {ratio}")

async def set_efx(self, effect: str, param: str, value) -> None:
    name = f"efx.{effect}_{param}" if param != "type" else None
    if name is None:
        return  # filter type change requires script reload — skip in Slice 5
    await self._telnet_send(f"{name}.set {float(value)}")

async def inject_tts(self, wav_path: str) -> None:
    await self._telnet_send(f"tts.push {wav_path}")
```

`FfmpegEngine`: same methods, no-op with warning.

Tests verify telnet commands.

Commit: `feat(dj_booth): pitch, EFX, TTS injection`.

---

### Task 3: Lifecycle wrappers

**File:** `helpers/lifecycle.py`

Add async functions: `set_pitch(deck, semitones)`, `set_efx(effect, param, value)`, `announce(text)`. The last calls into `helpers/tts.py` to produce a WAV, then `engine.inject_tts(path)`.

```python
async def set_pitch(deck: str, semitones: float) -> None:
    if _engine is None:
        return
    s = max(-6.0, min(6.0, float(semitones)))
    await _engine.set_pitch(deck, s)
    target = _state.get_state().deck_a if deck == "a" else _state.get_state().deck_b
    target.pitch = s


async def set_efx(effect: str, param: str, value) -> None:
    if _engine is None:
        return
    await _engine.set_efx(effect, param, value)
    s = _state.get_state().efx
    attr = f"{effect}_{param}" if param != "type" else "filter_type"
    if hasattr(s, attr):
        setattr(s, attr, value)


async def announce(text: str) -> None:
    if _engine is None or not text.strip():
        return
    from usr.plugins.dj_booth.helpers.tts import generate_tts_wav
    path = await generate_tts_wav(text)
    if path:
        await _engine.inject_tts(path)
```

Commit: `feat(dj_booth): lifecycle wrappers for pitch, EFX, announce`.

---

### Task 4: TTS helper + mic stub

**Files:** `helpers/tts.py`, `helpers/mic.py`, `tests/test_mic.py`.

`helpers/tts.py`:
```python
"""TTS WAV generator. Tries A0's speech helper, falls back to espeak-ng if available."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from typing import Optional

log = logging.getLogger(__name__)

TTS_DIR = "/tmp/dj_booth_tts"


async def generate_tts_wav(text: str) -> Optional[str]:
    if not text.strip():
        return None
    os.makedirs(TTS_DIR, exist_ok=True)
    out = os.path.join(TTS_DIR, f"{uuid.uuid4().hex}.wav")

    # Strategy 1: A0 speech helper (if exposed)
    try:
        from helpers.speech import synthesize_to_file  # type: ignore
        ok = await synthesize_to_file(text, out)
        if ok and os.path.exists(out):
            return out
    except Exception:
        pass

    # Strategy 2: espeak-ng subprocess
    if shutil.which("espeak-ng"):
        proc = await asyncio.create_subprocess_exec(
            "espeak-ng", "-w", out, text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await proc.wait()
        if rc == 0 and os.path.exists(out):
            return out

    log.warning("dj_booth: no TTS engine available (tried helpers.speech, espeak-ng)")
    return None
```

`helpers/mic.py`:
```python
"""Microphone capture stub — Slice 5 ships interface; full impl deferred."""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


class MicCapture:
    """Stub. start()/stop() return without doing anything; list_devices returns []."""
    _instance: Optional["MicCapture"] = None

    @classmethod
    def get(cls) -> "MicCapture":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.active = False
        self.volume = 0.8
        self.device_index = 0

    async def start(self, device_index: int = 0) -> bool:
        log.warning("dj_booth: mic capture not yet implemented (stub)")
        self.device_index = device_index
        self.active = False  # always remains False until real impl
        return False

    async def stop(self) -> None:
        self.active = False

    def set_volume(self, level: float) -> None:
        self.volume = max(0.0, min(2.0, float(level)))

    @staticmethod
    def list_devices() -> list[dict]:
        # Real impl: pyaudio.PyAudio().get_device_info_by_index(...)
        return []
```

Tests for mic stub: confirm singleton, start returns False, list_devices returns []. Don't test TTS — too env-dependent.

Commit: `feat(dj_booth): TTS WAV generator + mic capture stub`.

---

### Task 5: API + dj_tool

**Files:** `api/dj_control.py`, `tools/dj_tool.py`, tests.

`api/dj_control.py` new actions:
```python
elif action == "set_pitch":
    await lifecycle.set_pitch(input.get("deck", "a"), float(input.get("semitones", 0.0)))
elif action == "set_efx":
    await lifecycle.set_efx(input.get("effect", ""), input.get("param", ""), input.get("value", 0.0))
elif action == "announce":
    await lifecycle.announce(input.get("text", ""))
elif action == "sync_bpm":
    # Convenience: handled in tool layer; API just forwards to set_pitch
    src_bpm = float(input.get("source_bpm", 0.0))
    tgt_bpm = float(input.get("target_bpm", 0.0))
    deck = input.get("target_deck", "b")
    if src_bpm <= 0 or tgt_bpm <= 0:
        return self._error("sync_bpm requires source_bpm and target_bpm > 0")
    import math
    semitones = max(-6.0, min(6.0, 12.0 * math.log2(src_bpm / tgt_bpm)))
    await lifecycle.set_pitch(deck, semitones)
```

`tools/dj_tool.py` new sub-methods: `set_pitch`, `set_efx`, `announce`, `sync_bpm`.

`sync_bpm` reads BPM from library by path:
```python
elif method == "sync_bpm":
    from usr.plugins.dj_booth.api.dj_control import _get_library
    from usr.plugins.dj_booth.helpers import lifecycle
    import math
    lib = _get_library()
    src_path = self.args.get("source_path", "")
    tgt_path = self.args.get("target_path", "")
    target_deck = self.args.get("target_deck", "b")
    src = lib.get_track(src_path)
    tgt = lib.get_track(tgt_path)
    if not src or not tgt or not src.bpm or not tgt.bpm:
        return Response(message="sync_bpm: tracks must be analyzed first (BPM>0)", break_loop=False)
    semitones = max(-6.0, min(6.0, 12.0 * math.log2(src.bpm / tgt.bpm)))
    await lifecycle.set_pitch(target_deck, semitones)
    msg = f"sync'd deck {target_deck.upper()} to {src.bpm} BPM (pitch {semitones:+.2f} st)"
```

Tests: monkeypatch `_get_library` and `lifecycle.set_pitch`; assert pitch math.

Commit: `feat(dj_booth): API + dj_tool methods for pitch/EFX/announce/sync_bpm`.

---

### Task 6: Frontend — pitch slider + EFX rack

**Files:** `webui/dj-store.js`, `webui/dj-booth.html`.

Store: `setPitch(deck, semitones)`, `setEFX(effect, param, value)`, `announce(text)`. Getters `efx`, `deckA.pitch`, `deckB.pitch`.

HTML: Add pitch slider per deck (vertical or horizontal range, -6..+6).

```html
<label style="font-size: 0.75rem; color: #aaa;">
  Pitch <span x-text="$store.djBoothStore.deckA.pitch.toFixed(2) + ' st'"></span>
  <input type="range" min="-6" max="6" step="0.1"
         :value="$store.djBoothStore.deckA.pitch"
         @input="$store.djBoothStore.setPitch('a', parseFloat($event.target.value))">
</label>
```

Add EFX section to mixer panel:
```html
<div class="djb-mixer-section">
  <h4 style="font-size: 0.75rem; color: #ffbe0b; margin: 0.5rem 0 0.25rem;">EFX</h4>
  <label>Reverb <span x-text="(($store.djBoothStore.efx.reverb_wet||0)*100).toFixed(0)+'%'"></span>
    <input type="range" min="0" max="1" step="0.01"
           :value="$store.djBoothStore.efx.reverb_wet"
           @input="$store.djBoothStore.setEFX('reverb','wet',parseFloat($event.target.value))"></label>
  <label>Delay <span x-text="(($store.djBoothStore.efx.delay_wet||0)*100).toFixed(0)+'%'"></span>
    <input type="range" min="0" max="1" step="0.01"
           :value="$store.djBoothStore.efx.delay_wet"
           @input="$store.djBoothStore.setEFX('delay','wet',parseFloat($event.target.value))"></label>
  <label>Filter <span x-text="Math.round($store.djBoothStore.efx.filter_freq) + ' Hz'"></span>
    <input type="range" min="20" max="20000" step="10"
           :value="$store.djBoothStore.efx.filter_freq"
           @input="$store.djBoothStore.setEFX('filter','freq',parseFloat($event.target.value))"></label>
</div>
```

Add Announce text-and-button:
```html
<div class="djb-mixer-section">
  <h4 style="font-size: 0.75rem; color: #ffbe0b; margin: 0.5rem 0 0.25rem;">Announce</h4>
  <input class="djb-search" type="text" placeholder="say something to the listeners…"
         x-ref="ttsInput">
  <button class="djb-btn sm" style="margin-top: 0.25rem;"
          @click="$store.djBoothStore.announce($refs.ttsInput.value); $refs.ttsInput.value=''">Speak</button>
</div>
```

Commit: `feat(dj_booth): pitch slider + EFX rack + announce input`.

---

### Task 7: Hooks — pyaudio (best effort)

`hooks.py:install()` add `pyaudio>=0.2.14` to py_packages and `portaudio19-dev` to apt. Wrap pyaudio install in try/except since it commonly fails on hosts without portaudio:

```python
# pyaudio install can fail without portaudio; isolate
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "--quiet", "pyaudio>=0.2.14"],
    capture_output=True, text=True,
)
if result.returncode != 0:
    print(f"[dj_booth] WARNING: pyaudio install failed (mic disabled): {result.stderr.strip()}")
```

Commit: `feat(dj_booth): install pyaudio + portaudio (Slice 5)`.

---

### Task 8: Close-out

```bash
cd /Users/lazy/Desktop/agent-zero
python -m pytest usr/plugins/dj_booth/tests/ -v 2>&1 | tail -10
git tag -a dj_booth/slice-5-complete -m "dj_booth Slice 5: EFX, pitch, BPM sync, TTS, mic stub"
```

Update README "Status" to: "Slices 1-5 complete. dj_booth ships full DJ booth: 2 decks, mixer, EFX, pitch + BPM sync, TTS announcements, real-time spectrum, BPM/key analysis, library scan. Mic input stubbed (full impl deferred). Cue/loop/scratch deferred. Slice 3 liquidsoap script needs Docker integration test."

Commit README update.

Final tag, then plugin Slice 1-5 complete.
