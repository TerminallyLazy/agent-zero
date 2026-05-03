# dj_booth Slice 3 Implementation Plan — Two-Deck DJ Booth UI

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development. Steps use checkbox.

**Goal:** Replace Slice 1's single-stream control panel with a two-deck DJ booth — deck A and deck B with independent queues, crossfader, channel volumes, 3-band EQ per deck, basic waveform display. Backend grows from 1 source to 2-source mixer.

**Architecture:** Liquidsoap script becomes the real centerpiece — two `request.queue` sources, `cross.smart` or manual mix bus driven by a `ref(crossfader_pos)`, three-band `eq` per deck, master amplify. ffmpeg fallback retains its single-stream behavior (no live mixing possible without liquidsoap) but is deck-aware: `queue_track` accepts a `deck` arg and ffmpeg ignores it (always plays sequential). State adds `DeckState` × 2 + `MixerState`. UI rebuilds with two-column deck layout + center mixer + bottom library.

**MVP scope (this slice ships):** 2 decks, crossfader, channel volumes, 3-band EQ, simple stacked-bar waveform per deck, Now Playing per deck, deck-targeted queue_track / skip / clear.

**Deferred (cosmetic/non-architectural):**
- SVG spinning turntable (Slice 3.5 polish)
- Pitch slider, scratch on vinyl drag (Slice 5)
- Virtual scroll for huge libraries (later — CSS scroll fine for now)
- Track upload (later)
- Cue points, loop regions, BPM sync (Slice 5)

**Spec ref:** `BUILD_DOCS/A0-SHOUTCAST-SPEC.md` "DJ Booth UI" section + Slice 1 spec §15.

---

## File changes

```
usr/plugins/dj_booth/
├── helpers/
│   ├── state.py         MODIFY — add DeckState, MixerState, expand StreamState
│   ├── engine.py        MODIFY — 2-deck liquidsoap script + telnet routing
│   └── lifecycle.py     MODIFY — queue/skip/clear take deck arg
├── api/
│   └── dj_control.py    MODIFY — new actions: set_crossfader, set_volume, set_eq;
│                                  queue_track/skip/clear take deck arg
├── webui/
│   ├── dj-store.js      MODIFY — deck-aware methods, mixer/eq state
│   └── dj-booth.html    REWRITE — 2-deck layout + center mixer
└── tests/
    ├── test_state.py    MODIFY — DeckState/MixerState tests
    ├── test_engine.py   MODIFY — 2-deck liq script tests
    └── test_lifecycle.py MODIFY — deck-targeted lifecycle tests
```

No new files. All Slice 1+2 modules grow additively. Slice 1 fields kept for back-compat — old `current_track`, `queue` mirror deck A.

---

## Conventions

- **Deck IDs**: `"a"` and `"b"` everywhere — strings, not enums. Validates as `if deck not in ("a", "b"): raise`.
- **Liquidsoap deck naming**: queue ids are `deck_a`, `deck_b`. Telnet commands like `deck_a.push <path>`, `deck_a.skip`.
- **EQ ranges**: -12 to +12 dB. Center 0.
- **Crossfader**: 0.0 = full deck A, 1.0 = full deck B, 0.5 = balanced.
- **ffmpeg fallback** can't mix two streams. When liquidsoap is absent, the engine routes ALL queue_track calls to a single internal queue and treats `deck` as advisory metadata only. The mixer + EQ controls become no-ops with a one-time toast warning.

---

## Tasks

### Task 1: State extensions

**Files:** `helpers/state.py` + `tests/test_state.py`

- [ ] Append to `tests/test_state.py`:

```python
def test_deck_state_defaults():
    from usr.plugins.dj_booth.helpers.state import DeckState
    d = DeckState()
    assert d.queue == []
    assert d.current_track == ""
    assert d.volume == 1.0
    assert d.eq_low == 0.0 and d.eq_mid == 0.0 and d.eq_high == 0.0


def test_mixer_state_defaults():
    from usr.plugins.dj_booth.helpers.state import MixerState
    m = MixerState()
    assert m.crossfader == 0.5
    assert m.master_volume == 0.8


def test_stream_state_has_decks():
    reset_state()
    s = get_state()
    assert hasattr(s, "deck_a") and hasattr(s, "deck_b")
    assert s.deck_a.volume == 1.0
    assert s.mixer.crossfader == 0.5


def test_reset_state_restores_decks():
    reset_state()
    s = get_state()
    s.deck_a.volume = 0.3
    s.mixer.crossfader = 0.9
    reset_state()
    assert s.deck_a.volume == 1.0
    assert s.mixer.crossfader == 0.5
```

- [ ] Modify `helpers/state.py`. Add `DeckState`, `MixerState` dataclasses. Extend `StreamState` to include `deck_a: DeckState`, `deck_b: DeckState`, `mixer: MixerState`. Keep Slice 1 fields (`current_track`, `queue`) — populate them from deck A in lifecycle for back-compat.

```python
# Add near top of file, after StreamState fields are imported
@dataclass
class DeckState:
    queue: list[str] = field(default_factory=list)
    current_track: str = ""
    volume: float = 1.0
    eq_low: float = 0.0
    eq_mid: float = 0.0
    eq_high: float = 0.0


@dataclass
class MixerState:
    crossfader: float = 0.5
    master_volume: float = 0.8
```

Update `StreamState` to add:
```python
    deck_a: DeckState = field(default_factory=DeckState)
    deck_b: DeckState = field(default_factory=DeckState)
    mixer: MixerState = field(default_factory=MixerState)
```

Update `reset_state` so that the in-place field copy includes the new dataclass instances.

- [ ] Run all state tests, confirm pass.
- [ ] Commit: `feat(dj_booth): add DeckState + MixerState (Slice 3)`.

---

### Task 2: Engine — 2-deck liquidsoap, deck-aware ffmpeg

**Files:** `helpers/engine.py` + `tests/test_engine.py`

- [ ] Update `LIQ_SCRIPT_TEMPLATE` in `engine.py` to:

```python
LIQ_SCRIPT_TEMPLATE = '''# dj_booth — generated, do not edit
set("server.telnet", true)
set("server.telnet.port", {telnet_port})
set("log.file", false)
set("log.stdout", true)

# Decks
deck_a_q = request.queue(id="deck_a")
deck_b_q = request.queue(id="deck_b")

deck_a = audio_to_stereo(deck_a_q)
deck_b = audio_to_stereo(deck_b_q)

# 3-band EQ per deck (server-controlled refs)
eq_low_a  = interactive.float("deck_a.eq_low",  0.0)
eq_mid_a  = interactive.float("deck_a.eq_mid",  0.0)
eq_high_a = interactive.float("deck_a.eq_high", 0.0)
eq_low_b  = interactive.float("deck_b.eq_low",  0.0)
eq_mid_b  = interactive.float("deck_b.eq_mid",  0.0)
eq_high_b = interactive.float("deck_b.eq_high", 0.0)

deck_a = ladspa.tap_equalizer(deck_a, low={{eq_low_a}}, mid={{eq_mid_a}}, high={{eq_high_a}})
deck_b = ladspa.tap_equalizer(deck_b, low={{eq_low_b}}, mid={{eq_mid_b}}, high={{eq_high_b}})

# Channel volumes (server-controlled)
vol_a = interactive.float("deck_a.volume", 1.0)
vol_b = interactive.float("deck_b.volume", 1.0)
deck_a = amplify({{vol_a}}, deck_a)
deck_b = amplify({{vol_b}}, deck_b)

# Crossfader: 0=A, 1=B
xf = interactive.float("mixer.crossfader", 0.5)
mix = add([
  amplify({{1.0 - !xf}}, deck_a),
  amplify({{!xf}}, deck_b)
])

# Master
master_v = interactive.float("mixer.master_volume", 0.8)
mix = amplify({{master_v}}, mix)
mix = mksafe(mix)

output.icecast(
  %mp3(bitrate={bitrate}),
  host="localhost",
  port={icecast_port},
  password="{source_password}",
  mount="{mount}",
  name="{stream_name}",
  description="{stream_description}",
  genre="{stream_genre}",
  url="{stream_url}",
  public={public_int},
  mix
)
'''
```

(Note the doubled `{{ }}` are literal `{` and `}` after Python's `.format()` — ladspa params are bare names, the interactive refs.)

- [ ] Update `LiquidsoapEngine` methods to accept a `deck` arg ("a" or "b"):

```python
async def queue_track(self, path: str, deck: str = "a") -> None:
    queue_id = "deck_a" if deck == "a" else "deck_b"
    await self._telnet_send(f"{queue_id}.push {path}")

async def skip(self, deck: str = "a") -> None:
    queue_id = "deck_a" if deck == "a" else "deck_b"
    await self._telnet_send(f"{queue_id}.skip")

async def clear_queue(self, deck: str = "a") -> None:
    queue_id = "deck_a" if deck == "a" else "deck_b"
    for _ in range(100):
        resp = await self._telnet_send(f"{queue_id}.length")
        try:
            if int(resp.strip()) == 0:
                return
        except ValueError:
            return
        await self._telnet_send(f"{queue_id}.skip")

async def get_current(self, deck: str = "a") -> Optional[str]:
    # request.on_air returns the on-air rid for whichever queue has audio out;
    # we use the per-queue "remaining" trick: query deck_a.queue for current.
    try:
        rid = (await self._telnet_send(f"{'deck_a' if deck == 'a' else 'deck_b'}.queue")).strip().split("\n")[0].strip()
        if not rid:
            return None
        meta = await self._telnet_send(f"request.metadata {rid}")
        artist = title = ""
        for line in meta.splitlines():
            if line.startswith('artist="'):
                artist = line.split('"', 2)[1]
            elif line.startswith('title="'):
                title = line.split('"', 2)[1]
        if artist or title:
            return f"{artist} - {title}".strip(" -")
        return None
    except Exception:
        return None

async def set_crossfader(self, value: float) -> None:
    v = max(0.0, min(1.0, float(value)))
    await self._telnet_send(f"mixer.crossfader.set {v}")

async def set_volume(self, target: str, value: float) -> None:
    """target: 'deck_a' | 'deck_b' | 'master'"""
    v = max(0.0, min(2.0, float(value)))
    if target == "master":
        await self._telnet_send(f"mixer.master_volume.set {v}")
    else:
        await self._telnet_send(f"{target}.volume.set {v}")

async def set_eq(self, deck: str, low: float, mid: float, high: float) -> None:
    deck_q = "deck_a" if deck == "a" else "deck_b"
    for band, val in [("low", low), ("mid", mid), ("high", high)]:
        v = max(-12.0, min(12.0, float(val)))
        await self._telnet_send(f"{deck_q}.eq_{band}.set {v}")
```

- [ ] Update `FfmpegEngine` methods to accept `deck` arg but ignore it (warn once on mixer ops):

```python
async def queue_track(self, path: str, deck: str = "a") -> None:
    await self.queue.put(path)  # deck arg ignored in fallback

async def skip(self, deck: str = "a") -> None:
    await self._kill_current()

async def clear_queue(self, deck: str = "a") -> None:
    while not self.queue.empty():
        self.queue.get_nowait()

async def set_crossfader(self, value: float) -> None:
    log.warning("dj_booth: ffmpeg fallback ignores crossfader")

async def set_volume(self, target: str, value: float) -> None:
    log.warning("dj_booth: ffmpeg fallback ignores volume")

async def set_eq(self, deck: str, low: float, mid: float, high: float) -> None:
    log.warning("dj_booth: ffmpeg fallback ignores EQ")

async def get_current(self, deck: str = "a") -> Optional[str]:
    if deck != "a":
        return None  # ffmpeg only plays one stream
    return self._current_path or None
```

- [ ] Update `StreamEngine` Protocol to reflect the new method signatures (add `deck: str = "a"` defaults; add `set_crossfader`, `set_volume`, `set_eq`).

- [ ] Update existing test `test_liquidsoap_engine_telnet_round_trip` so it asserts `deck_a.push` (not `main.push`) for default deck. Add a new test for deck B routing. Add tests that confirm `set_crossfader` and `set_eq` send the right telnet commands.

```python
@pytest.mark.asyncio
async def test_liquidsoap_engine_deck_b_routing(monkeypatch):
    eng = LiquidsoapEngine()
    sent = []
    async def fake(cmd):
        sent.append(cmd); return ""
    monkeypatch.setattr(eng, "_telnet_send", fake)
    await eng.queue_track("/b.mp3", deck="b")
    assert sent[-1] == "deck_b.push /b.mp3"
    await eng.skip(deck="b")
    assert sent[-1] == "deck_b.skip"


@pytest.mark.asyncio
async def test_liquidsoap_engine_set_crossfader_eq(monkeypatch):
    eng = LiquidsoapEngine()
    sent = []
    async def fake(cmd):
        sent.append(cmd); return ""
    monkeypatch.setattr(eng, "_telnet_send", fake)
    await eng.set_crossfader(0.7)
    assert sent[-1] == "mixer.crossfader.set 0.7"
    await eng.set_eq("a", -3.0, 1.5, 6.0)
    assert "deck_a.eq_low.set -3.0" in sent
    assert "deck_a.eq_mid.set 1.5" in sent
    assert "deck_a.eq_high.set 6.0" in sent
```

Update existing render-script test to match the new template (check for `deck_a_q`, `deck_b_q`, `mixer.crossfader`, `interactive.float`).

- [ ] Run engine tests, confirm pass.
- [ ] Commit: `feat(dj_booth): 2-deck liquidsoap engine with crossfader + EQ`.

---

### Task 3: Lifecycle + API — deck-aware actions

**Files:** `helpers/lifecycle.py` + `api/dj_control.py` + tests.

- [ ] Update `lifecycle.py`:

```python
async def queue_track(path: str, deck: str = "a") -> None:
    s = _state.get_state()
    if not s.is_running or _engine is None:
        raise RuntimeError("stream not running")
    if deck not in ("a", "b"):
        raise ValueError(f"invalid deck: {deck}")
    await _engine.queue_track(path, deck)
    target = s.deck_a if deck == "a" else s.deck_b
    target.queue.append(path)
    if deck == "a":
        s.queue.append(path)  # back-compat mirror


async def skip_current(deck: str = "a") -> None:
    if _engine is None:
        raise RuntimeError("stream not running")
    await _engine.skip(deck)


async def clear_queue(deck: str = "a") -> None:
    s = _state.get_state()
    if _engine is None:
        return
    await _engine.clear_queue(deck)
    target = s.deck_a if deck == "a" else s.deck_b
    target.queue.clear()
    if deck == "a":
        s.queue.clear()


async def set_crossfader(value: float) -> None:
    if _engine is None:
        return
    await _engine.set_crossfader(value)
    _state.get_state().mixer.crossfader = max(0.0, min(1.0, float(value)))


async def set_volume(target: str, value: float) -> None:
    if _engine is None:
        return
    await _engine.set_volume(target, value)
    s = _state.get_state()
    v = max(0.0, min(2.0, float(value)))
    if target == "deck_a":
        s.deck_a.volume = v
    elif target == "deck_b":
        s.deck_b.volume = v
    elif target == "master":
        s.mixer.master_volume = v


async def set_eq(deck: str, low: float, mid: float, high: float) -> None:
    if _engine is None:
        return
    await _engine.set_eq(deck, low, mid, high)
    s = _state.get_state()
    target = s.deck_a if deck == "a" else s.deck_b
    target.eq_low = max(-12.0, min(12.0, float(low)))
    target.eq_mid = max(-12.0, min(12.0, float(mid)))
    target.eq_high = max(-12.0, min(12.0, float(high)))
```

- [ ] Update `_health_loop` to call `engine.get_current("a")` and `("b")` and write to `s.deck_a.current_track` and `s.deck_b.current_track`. Mirror deck A current to legacy `s.current_track`.

- [ ] Update `api/dj_control.py` to dispatch new actions:

```python
elif action == "queue_track":
    path = input.get("path", "")
    deck = input.get("deck", "a")
    if not path:
        return self._error("missing 'path'")
    await lifecycle.queue_track(path, deck)
elif action == "skip":
    await lifecycle.skip_current(input.get("deck", "a"))
elif action == "clear_queue":
    await lifecycle.clear_queue(input.get("deck", "a"))
elif action == "set_crossfader":
    await lifecycle.set_crossfader(float(input.get("position", 0.5)))
elif action == "set_volume":
    await lifecycle.set_volume(input.get("channel", "deck_a"), float(input.get("level", 1.0)))
elif action == "set_eq":
    await lifecycle.set_eq(
        input.get("deck", "a"),
        float(input.get("low", 0.0)),
        float(input.get("mid", 0.0)),
        float(input.get("high", 0.0)),
    )
```

(The existing `start`, `stop`, `scan_library` actions stay unchanged.)

- [ ] Update `dj_tool.py` to add deck arg pass-through for `queue_track`, `skip`, `clear_queue`. Add new methods `set_crossfader`, `set_volume`, `set_eq`. Add tests.

- [ ] Add lifecycle tests for new actions:

```python
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
```

- [ ] Run all tests, confirm pass.
- [ ] Commit: `feat(dj_booth): deck-aware lifecycle and API actions`.

---

### Task 4: Frontend store — deck-aware methods + mixer state

**File:** `webui/dj-store.js`

Add deck-aware methods:

```javascript
async queueTrack(path, deck = "a") {
    const r = await this._control("queue_track", { path, deck });
    if (r && !r.error) toastFrontendInfo(`Queued on deck ${deck.toUpperCase()}`, "DJ Booth");
},
async skip(deck = "a") { await this._control("skip", { deck }); },
async clearQueue(deck = "a") { await this._control("clear_queue", { deck }); },
async setCrossfader(position) { await this._control("set_crossfader", { position }); },
async setVolume(channel, level) { await this._control("set_volume", { channel, level }); },
async setEQ(deck, low, mid, high) { await this._control("set_eq", { deck, low, mid, high }); },

// Selected deck — UI tracks which deck is the "active" target for library double-click
selectedDeck: "a",
selectDeck(d) { this.selectedDeck = d; },

// Convenience getters
get deckA() { return this.status?.deck_a || { queue: [], current_track: "", volume: 1.0, eq_low: 0, eq_mid: 0, eq_high: 0 }; },
get deckB() { return this.status?.deck_b || { queue: [], current_track: "", volume: 1.0, eq_low: 0, eq_mid: 0, eq_high: 0 }; },
get mixer() { return this.status?.mixer || { crossfader: 0.5, master_volume: 0.8 }; },
```

Replace existing `queueTrack`/`skip`/`clearQueue` with the deck-aware versions above. `currentTrack` getter now returns `deckA.current_track` for back-compat or both decks (caller picks).

Commit: `feat(dj_booth): deck-aware frontend store`.

---

### Task 5: Frontend modal — 2-deck layout + mixer

**File:** `webui/dj-booth.html` (full rewrite)

Layout:
```
┌─────────── HEADER ───────────────────────┐
│ Station | Engine | Listeners | Stream URL│
├─────── DECK A ───┬─ MIXER ──┬─── DECK B ─┤
│ Now Playing      │ Master   │ Now Playing│
│ Waveform bars    │ Volume   │ Waveform   │
│ Queue            │ Crossfade│ Queue      │
│ Vol fader        │          │ Vol fader  │
│ EQ low/mid/high  │          │ EQ knobs   │
│ Skip / Clear     │          │ Skip/Clear │
├──────── LIBRARY (full width) ────────────┤
│ Search │ Sort │ Track list │ "→A" "→B"  │
└──────────────────────────────────────────┘
```

Knob = `<input type="range" min="-12" max="12" step="0.5">` styled compact for MVP. Real rotary SVG knobs deferred to polish slice.

Waveform = simple stacked bar chart of queue length proxy (no real audio FFT — that's Slice 4). For MVP, render as 32 bars all at uniform height when playing, all gray when idle. This proves the canvas wiring; Slice 4 swaps in real waveform peaks.

Crossfader: `<input type="range" min="0" max="1" step="0.01" :value="mixer.crossfader" @input="setCrossfader($event.target.value)">`.

Library: each row gets two buttons "→A" "→B" instead of single double-click. Double-click queues on `selectedDeck`.

Full file contents (write verbatim):

```html
<head>
  <script type="module" src="/plugins/dj_booth/webui/dj-store.js"></script>
  <style>
    .djb-wrap { padding: 1rem; max-width: 1400px; margin: 0 auto; color: #e8e8f0; }
    .djb-header { display: flex; gap: 1rem; align-items: center; padding: 0.75rem 1rem;
                  background: #1a1a2e; border-radius: 8px; margin-bottom: 1rem; }
    .djb-badge { padding: 0.15rem 0.5rem; background: #16213e; border-radius: 4px;
                 font: 0.75rem 'JetBrains Mono', monospace; color: #00d4ff; }
    .djb-badge.fallback { color: #ffbe0b; }
    .djb-listeners { display: flex; align-items: center; gap: 0.4rem; font: 0.85rem monospace; }
    .djb-pulse { width: 8px; height: 8px; border-radius: 50%; background: #00ff88;
                 box-shadow: 0 0 8px #00ff88; animation: pulse 2s infinite; }
    @keyframes pulse { 50% { opacity: 0.3; } }
    .djb-stream-url { flex: 1; font: 0.8rem monospace; color: #aaa; }
    .djb-btn { padding: 0.4rem 0.9rem; border-radius: 4px; border: 1px solid #3a3a4e;
               background: #16213e; color: #e8e8f0; cursor: pointer; font-size: 0.85rem; }
    .djb-btn:hover { background: #233355; border-color: #00d4ff; }
    .djb-btn.start { background: #00ff88; color: #001a0c; border-color: #00ff88; }
    .djb-btn.stop  { background: #ff006e; color: #fff; border-color: #ff006e; }
    .djb-btn.sm { padding: 0.2rem 0.5rem; font-size: 0.75rem; }
    .djb-grid { display: grid; grid-template-columns: 5fr 3fr 5fr; gap: 1rem; }
    .djb-panel { background: #1a1a2e; padding: 1rem; border-radius: 8px; }
    .djb-panel.deck-a { border-top: 3px solid #00d4ff; }
    .djb-panel.deck-b { border-top: 3px solid #ff006e; }
    .djb-panel.mixer { border-top: 3px solid #ffbe0b; }
    .djb-panel.selected { box-shadow: 0 0 16px rgba(0, 212, 255, 0.4); }
    .djb-panel h3 { margin-top: 0; font-size: 0.85rem; color: #00d4ff; text-transform: uppercase;
                    letter-spacing: 1px; }
    .djb-panel.deck-b h3 { color: #ff006e; }
    .djb-now { font: 1.05rem 'JetBrains Mono', monospace; padding: 0.4rem 0; min-height: 1.5rem; }
    .djb-waveform { display: flex; gap: 1px; height: 40px; align-items: end;
                    background: #0a0a0f; padding: 4px; border-radius: 4px; margin: 0.5rem 0; }
    .djb-bar { flex: 1; background: #00d4ff; opacity: 0.5; min-height: 2px; }
    .djb-panel.deck-b .djb-bar { background: #ff006e; }
    .djb-bar.active { opacity: 1; }
    .djb-list { max-height: 140px; overflow-y: auto; font: 0.8rem monospace; }
    .djb-list.lib { max-height: 220px; }
    .djb-row { display: grid; grid-template-columns: 1fr; padding: 0.25rem 0.4rem;
               cursor: pointer; border-radius: 3px; }
    .djb-row:hover { background: rgba(0, 212, 255, 0.1); }
    .djb-search { width: 100%; padding: 0.4rem; background: #0a0a0f;
                  border: 1px solid #3a3a4e; color: #e8e8f0; border-radius: 4px;
                  margin-bottom: 0.5rem; }
    .djb-empty { color: #888; font-style: italic; padding: 1rem; text-align: center; }
    .djb-controls { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
    .djb-fader { width: 100%; }
    .djb-eq { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.5rem; margin-top: 0.5rem; }
    .djb-eq label { font-size: 0.7rem; color: #aaa; display: flex; flex-direction: column; align-items: center; }
    .djb-eq input { width: 100%; }
    .djb-mixer-section { margin-bottom: 1rem; }
    .djb-mixer-section label { font-size: 0.75rem; color: #aaa; }
    .djb-cf { background: linear-gradient(to right, #00d4ff, #1a1a2e 50%, #ff006e);
              border-radius: 4px; height: 10px; }
    .djb-lib-row { display: grid; grid-template-columns: 1fr 1fr 60px 50px 50px;
                   gap: 0.5rem; padding: 0.3rem 0.4rem; cursor: pointer;
                   border-radius: 3px; align-items: center; }
    .djb-lib-row:hover { background: rgba(0, 212, 255, 0.1); }
    .djb-lib-btn { padding: 0.15rem 0.4rem; font-size: 0.7rem; }
    .djb-lib-btn.a { color: #00d4ff; border-color: #00d4ff; }
    .djb-lib-btn.b { color: #ff006e; border-color: #ff006e; }
  </style>
</head>

<div x-data>
  <template x-if="$store.djBoothStore">
    <div x-init="$store.djBoothStore.onOpen()" x-destroy="$store.djBoothStore.cleanup()" class="djb-wrap">

      <div class="djb-header">
        <h2 x-text="$store.djBoothStore.status?.is_running ? '🎧 ON AIR' : '🎧 DJ Booth'"
            style="margin: 0 1rem 0 0; font-size: 1.05rem;"></h2>
        <span class="djb-badge"
              :class="{ fallback: $store.djBoothStore.status?.engine === 'ffmpeg' }"
              x-text="$store.djBoothStore.engineLabel"></span>
        <div class="djb-listeners" x-show="$store.djBoothStore.isRunning">
          <span class="djb-pulse"></span>
          <span x-text="$store.djBoothStore.listenerCount + ' listening'"></span>
        </div>
        <div class="djb-stream-url"
             x-text="$store.djBoothStore.status?.stream_url || ''"
             x-show="$store.djBoothStore.isRunning"></div>
        <button class="djb-btn" x-show="$store.djBoothStore.isRunning"
                @click="$store.djBoothStore.copyStreamUrl()">Copy URL</button>
        <button class="djb-btn start" x-show="!$store.djBoothStore.isRunning"
                @click="$store.djBoothStore.start()">Start</button>
        <button class="djb-btn stop" x-show="$store.djBoothStore.isRunning"
                @click="$store.djBoothStore.stop()">Stop</button>
      </div>

      <div class="djb-grid">

        <!-- DECK A -->
        <div class="djb-panel deck-a"
             :class="{ selected: $store.djBoothStore.selectedDeck === 'a' }"
             @click="$store.djBoothStore.selectDeck('a')">
          <h3>Deck A</h3>
          <div class="djb-now" x-text="$store.djBoothStore.deckA.current_track || '— silence —'"></div>
          <div class="djb-waveform">
            <template x-for="i in 32" :key="i">
              <div class="djb-bar" :class="{ active: $store.djBoothStore.deckA.current_track }"></div>
            </template>
          </div>
          <h3>Queue (<span x-text="$store.djBoothStore.deckA.queue.length"></span>)</h3>
          <div class="djb-list">
            <template x-for="(p, i) in $store.djBoothStore.deckA.queue" :key="i">
              <div class="djb-row"><span x-text="p.split('/').pop()"></span></div>
            </template>
            <div class="djb-empty" x-show="!$store.djBoothStore.deckA.queue.length">queue empty</div>
          </div>
          <div class="djb-controls">
            <button class="djb-btn sm" @click.stop="$store.djBoothStore.skip('a')"
                    :disabled="!$store.djBoothStore.isRunning">Skip</button>
            <button class="djb-btn sm" @click.stop="$store.djBoothStore.clearQueue('a')"
                    :disabled="!$store.djBoothStore.isRunning">Clear</button>
          </div>
          <label style="font-size: 0.75rem; color: #aaa; display: block; margin-top: 0.5rem;">
            Volume <span x-text="$store.djBoothStore.deckA.volume.toFixed(2)"></span>
            <input class="djb-fader" type="range" min="0" max="2" step="0.05"
                   :value="$store.djBoothStore.deckA.volume"
                   @input="$store.djBoothStore.setVolume('deck_a', parseFloat($event.target.value))">
          </label>
          <div class="djb-eq">
            <label>Low <span x-text="$store.djBoothStore.deckA.eq_low.toFixed(1)"></span>
              <input type="range" min="-12" max="12" step="0.5"
                     :value="$store.djBoothStore.deckA.eq_low"
                     @change="$store.djBoothStore.setEQ('a',
                                parseFloat($event.target.value),
                                $store.djBoothStore.deckA.eq_mid,
                                $store.djBoothStore.deckA.eq_high)"></label>
            <label>Mid <span x-text="$store.djBoothStore.deckA.eq_mid.toFixed(1)"></span>
              <input type="range" min="-12" max="12" step="0.5"
                     :value="$store.djBoothStore.deckA.eq_mid"
                     @change="$store.djBoothStore.setEQ('a',
                                $store.djBoothStore.deckA.eq_low,
                                parseFloat($event.target.value),
                                $store.djBoothStore.deckA.eq_high)"></label>
            <label>High <span x-text="$store.djBoothStore.deckA.eq_high.toFixed(1)"></span>
              <input type="range" min="-12" max="12" step="0.5"
                     :value="$store.djBoothStore.deckA.eq_high"
                     @change="$store.djBoothStore.setEQ('a',
                                $store.djBoothStore.deckA.eq_low,
                                $store.djBoothStore.deckA.eq_mid,
                                parseFloat($event.target.value))"></label>
          </div>
        </div>

        <!-- MIXER -->
        <div class="djb-panel mixer">
          <h3 style="color: #ffbe0b;">Mixer</h3>

          <div class="djb-mixer-section">
            <label>Master <span x-text="$store.djBoothStore.mixer.master_volume.toFixed(2)"></span>
              <input class="djb-fader" type="range" min="0" max="1.5" step="0.05"
                     :value="$store.djBoothStore.mixer.master_volume"
                     @input="$store.djBoothStore.setVolume('master', parseFloat($event.target.value))"></label>
          </div>

          <div class="djb-mixer-section">
            <label>Crossfader (A ←→ B) <span x-text="$store.djBoothStore.mixer.crossfader.toFixed(2)"></span></label>
            <input class="djb-fader" type="range" min="0" max="1" step="0.01"
                   :value="$store.djBoothStore.mixer.crossfader"
                   @input="$store.djBoothStore.setCrossfader(parseFloat($event.target.value))">
            <div class="djb-cf"></div>
          </div>

          <div style="margin-top: 1rem; font-size: 0.75rem; color: #888;">
            Selected deck: <strong x-text="$store.djBoothStore.selectedDeck.toUpperCase()"></strong>
            <br>Library double-click queues here.
          </div>
        </div>

        <!-- DECK B -->
        <div class="djb-panel deck-b"
             :class="{ selected: $store.djBoothStore.selectedDeck === 'b' }"
             @click="$store.djBoothStore.selectDeck('b')">
          <h3>Deck B</h3>
          <div class="djb-now" x-text="$store.djBoothStore.deckB.current_track || '— silence —'"></div>
          <div class="djb-waveform">
            <template x-for="i in 32" :key="i">
              <div class="djb-bar" :class="{ active: $store.djBoothStore.deckB.current_track }"></div>
            </template>
          </div>
          <h3>Queue (<span x-text="$store.djBoothStore.deckB.queue.length"></span>)</h3>
          <div class="djb-list">
            <template x-for="(p, i) in $store.djBoothStore.deckB.queue" :key="i">
              <div class="djb-row"><span x-text="p.split('/').pop()"></span></div>
            </template>
            <div class="djb-empty" x-show="!$store.djBoothStore.deckB.queue.length">queue empty</div>
          </div>
          <div class="djb-controls">
            <button class="djb-btn sm" @click.stop="$store.djBoothStore.skip('b')"
                    :disabled="!$store.djBoothStore.isRunning">Skip</button>
            <button class="djb-btn sm" @click.stop="$store.djBoothStore.clearQueue('b')"
                    :disabled="!$store.djBoothStore.isRunning">Clear</button>
          </div>
          <label style="font-size: 0.75rem; color: #aaa; display: block; margin-top: 0.5rem;">
            Volume <span x-text="$store.djBoothStore.deckB.volume.toFixed(2)"></span>
            <input class="djb-fader" type="range" min="0" max="2" step="0.05"
                   :value="$store.djBoothStore.deckB.volume"
                   @input="$store.djBoothStore.setVolume('deck_b', parseFloat($event.target.value))">
          </label>
          <div class="djb-eq">
            <label>Low <span x-text="$store.djBoothStore.deckB.eq_low.toFixed(1)"></span>
              <input type="range" min="-12" max="12" step="0.5"
                     :value="$store.djBoothStore.deckB.eq_low"
                     @change="$store.djBoothStore.setEQ('b',
                                parseFloat($event.target.value),
                                $store.djBoothStore.deckB.eq_mid,
                                $store.djBoothStore.deckB.eq_high)"></label>
            <label>Mid <span x-text="$store.djBoothStore.deckB.eq_mid.toFixed(1)"></span>
              <input type="range" min="-12" max="12" step="0.5"
                     :value="$store.djBoothStore.deckB.eq_mid"
                     @change="$store.djBoothStore.setEQ('b',
                                $store.djBoothStore.deckB.eq_low,
                                parseFloat($event.target.value),
                                $store.djBoothStore.deckB.eq_high)"></label>
            <label>High <span x-text="$store.djBoothStore.deckB.eq_high.toFixed(1)"></span>
              <input type="range" min="-12" max="12" step="0.5"
                     :value="$store.djBoothStore.deckB.eq_high"
                     @change="$store.djBoothStore.setEQ('b',
                                $store.djBoothStore.deckB.eq_low,
                                $store.djBoothStore.deckB.eq_mid,
                                parseFloat($event.target.value))"></label>
          </div>
        </div>
      </div>

      <!-- LIBRARY -->
      <div class="djb-panel" style="margin-top: 1rem;">
        <h3>Library
          <button class="djb-btn sm" style="float:right;" @click="$store.djBoothStore.scanLibrary()">Scan</button>
        </h3>
        <input class="djb-search" type="text" placeholder="search title / artist / album"
               :value="$store.djBoothStore.librarySearch"
               @input.debounce.300ms="$store.djBoothStore.onSearchChange($event.target.value)">
        <div class="djb-list lib">
          <template x-for="t in $store.djBoothStore.library.tracks" :key="t.path">
            <div class="djb-lib-row" :title="t.path"
                 @dblclick="$store.djBoothStore.queueTrack(t.path, $store.djBoothStore.selectedDeck)">
              <span x-text="t.title"></span>
              <span x-text="t.artist" style="color:#aaa;"></span>
              <span x-text="t.format" style="color:#666;"></span>
              <button class="djb-btn djb-lib-btn a"
                      @click.stop="$store.djBoothStore.queueTrack(t.path, 'a')">→A</button>
              <button class="djb-btn djb-lib-btn b"
                      @click.stop="$store.djBoothStore.queueTrack(t.path, 'b')">→B</button>
            </div>
          </template>
          <div class="djb-empty" x-show="!$store.djBoothStore.library.tracks.length">
            no tracks — click Scan
          </div>
        </div>
      </div>

    </div>
  </template>
</div>
```

Commit: `feat(dj_booth): 2-deck DJ booth UI with mixer + EQ`.

---

### Task 6: Slice 3 close-out

- [ ] Run all tests, expect pass count = Slice 2 (32) + new tests (~10) ≈ 42
- [ ] Tag `dj_booth/slice-3-complete`
- [ ] Update README.md to reflect Slice 3 scope
