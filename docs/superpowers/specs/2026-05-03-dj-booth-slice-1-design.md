# dj_booth — Slice 1 Design (Stream Backbone)

**Plugin:** `usr/plugins/dj_booth/`
**Slice:** 1 of 5 (stream backbone, no agent tool, no advanced UI)
**Source spec:** `BUILD_DOCS/A0-SHOUTCAST-SPEC.md`

## 1. Purpose

Ship a minimum-viable Icecast2 streaming plugin for Agent Zero. After Slice 1, a user can install the plugin, click Execute, and have any ICY-compatible client (VLC, Winamp, browser) tune into a working audio stream sourced from a local music directory. No agent autonomy, no DJ booth UI, no analysis — those are Slices 2–5.

## 2. Decomposition Rationale

The full `A0-SHOUTCAST-SPEC.md` describes seven independent subsystems (Icecast, Liquidsoap, BPM/key analysis, spectrum FFT, waveforms, mic capture, full DJ UI, agent tool). Implementing all at once produces 5000+ LOC with high integration debt. Slicing vertically lets each release ship in days instead of weeks.

| Slice | Scope | This doc |
|---|---|---|
| 1 | Stream backbone: Icecast + engine + library + minimal UI | ✅ |
| 2 | Agent `dj_tool`, agent profile, system prompt extension | future |
| 3 | DJ booth UI: 2 decks, mixer, waveforms, library browser | future |
| 4 | Analysis: BPM (aubio), key (chromagram), spectrum, pre-computed waveforms | future |
| 5 | Performance: EFX rack, mic input, scratch, cue/loop, BPM sync | future |

Each slice gets its own design doc, plan, and implementation cycle.

## 3. Architecture

```
A0 Plugin runtime (Python, async)
  ├─ helpers/state.py        StreamState singleton (slim — Slice 1 fields only)
  ├─ helpers/icecast.py      IcecastManager: write xml, spawn icecast2, poll status
  ├─ helpers/engine.py       StreamEngine Protocol
  │   ├─ LiquidsoapEngine    .liq script + telnet control on :1234
  │   └─ FfmpegEngine        sequential ffmpeg → icecast (no crossfade) fallback
  ├─ helpers/library.py      LibraryManager: walk dir, mutagen tags
  ├─ api/dj_control.py       multi-action POST: start/stop/queue/skip/clear/scan
  ├─ api/stream_status.py    GET+POST status JSON
  ├─ api/library.py          POST list/search
  └─ webui/                  minimal control panel (no decks/EFX)

External processes (subprocess via asyncio.create_subprocess_exec):
  icecast2     ← /tmp/dj_booth_icecast.xml
  liquidsoap   ← /tmp/dj_booth.liq      (preferred)
  ffmpeg       ← per-track invocations  (fallback)

All temp files under /tmp/dj_booth_* — no permanent system writes.
```

The `StreamEngine` interface is the key abstraction. It lets Slice 1 ship without forcing a hard liquidsoap dependency, and lets Slices 3–5 add deck B, EFX, and analysis behind the same surface.

## 4. Engine Interface

```python
from typing import Protocol

class StreamEngine(Protocol):
    async def start(self, config: dict, initial_tracks: list[str]) -> None: ...
    async def stop(self) -> None: ...
    async def queue_track(self, path: str) -> None: ...
    async def skip(self) -> None: ...
    async def clear_queue(self) -> None: ...
    async def is_alive(self) -> bool: ...
    async def get_current(self) -> str | None: ...
```

### 4.1 LiquidsoapEngine

Generates `/tmp/dj_booth.liq`:

```liquidsoap
set("server.telnet", true)
set("server.telnet.port", 1234)
set("log.file", false)
set("log.stdout", true)

queue = request.queue(id="main")
source = audio_to_stereo(queue)
source = mksafe(source)

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
  source
)
```

Telnet commands used in Slice 1:
- `main.push <uri>` — queue a track
- `main.skip` — skip current
- `main.consume` — clear remaining queue (if available; else loop `main.skip`)
- `request.on_air` — current request id
- `request.metadata <id>` — fetch title/artist for current

Connection: open per-call asyncio TCP, send command + `\n`, read until `END\r\n`, close.

### 4.2 FfmpegEngine (fallback)

Selected when `shutil.which("liquidsoap")` returns `None`.

State: `asyncio.Queue[str]` of track paths + a single `asyncio.subprocess.Process` reference for the currently-streaming track.

Loop task:
1. `await queue.get()` → track path
2. Spawn `ffmpeg -re -i <path> -c:a libmp3lame -b:a {bitrate}k -ar {sample_rate} -ac 2 -content_type audio/mpeg -f mp3 icecast://source:{source_password}@localhost:{port}{mount}`
3. `await proc.wait()` — track finishes naturally or is killed by `skip()`
4. Loop

`skip()` = `proc.terminate()`; loop advances. `stop()` cancels the loop task and terminates any current proc. Brief silence between tracks is expected and documented as a fallback limitation.

### 4.3 Engine selection at start

```python
def select_engine() -> StreamEngine:
    if shutil.which("liquidsoap"):
        return LiquidsoapEngine()
    return FfmpegEngine()
```

The selected engine name is written to `StreamState.engine` and surfaced in the UI as a badge.

### 4.4 Engine failure semantics

Engine selection happens once per `start()` call. Slice 1 does **not** auto-swap engines mid-session — that hides bugs and makes behavior unpredictable.

| When | What happens |
|---|---|
| `start()` and liquidsoap binary missing | Select ffmpeg engine, log info, badge `FFMPEG (fallback)` |
| `start()` and liquidsoap fails to spawn (binary present, exits non-zero) | Set `state.error`, set `is_running=False`, AgentNotification.error toast. Do NOT auto-retry with ffmpeg. User clicks Start again to retry. |
| Liquidsoap telnet connect fails after spawn | Retry 3× with 200ms backoff; if still failing, mark engine dead (same path as crash mid-stream) |
| Engine crashes mid-stream | Health-check task (5s cadence) detects via `is_alive()`. Set `state.error`, set `is_running=False`, surface toast. Stream stops. User must click Start to resume. |
| ffmpeg per-track spawn fails | Skip to next track in queue, log warning, increment internal failure counter; if 3 consecutive failures → same path as engine crash |

Rationale: Slice 1 prefers loud, observable failures over silent fallback chains. Slice 4+ may add smarter recovery once observability is richer.

## 5. Process & State Management

### 5.1 Subprocess lifecycle

All processes spawned via `asyncio.create_subprocess_exec`. PIDs stored in singleton state. Stdout/stderr piped to log files in `/tmp/dj_booth_logs/`.

A module-level `asyncio.Lock` (`_lifecycle_lock`) wraps every `start()` and `stop()` call. Concurrent POSTs to `dj_control` with `action=start` while a start is in progress wait on the lock and then short-circuit if `is_running` is already true (idempotent). Same for `stop`.

**Pre-start checks** (run before spawning anything):
1. Stale-PID sweep: read any existing `/tmp/dj_booth_*.pid`. For each PID still running (`os.kill(pid, 0)` succeeds), SIGTERM and wait 2s, SIGKILL if needed. Then unlink the pidfile. Logged so user sees what was cleaned up.
2. Port bind probe: `socket.socket().bind(("0.0.0.0", icecast_port))` — if `OSError` raised, abort with `state.error="Port {port} in use"` and toast. Do not spawn icecast.
3. Config validation: re-read config from disk via `get_plugin_config("dj_booth")` (defends against direct yaml edits between save and start). Validate required fields present and ports are integers in range. Abort on failure with specific error message.

Graceful stop sequence (in order, holding `_lifecycle_lock`):
1. Cancel `_health_loop` task
2. Engine: telnet `quit` to liquidsoap, or cancel ffmpeg loop task and `proc.terminate()` any current ffmpeg child
3. Wait up to 3s for engine to exit; SIGKILL via stored PID if not
4. Icecast: SIGTERM via `os.kill(pid, signal.SIGTERM)`
5. Wait up to 5s; SIGKILL if not
6. Verify with `os.kill(pid, 0)` for each tracked PID — if any still alive, log error and force-kill
7. Remove pidfiles in `/tmp/dj_booth_*.pid`
8. Reset state to defaults except `library_count` and last-known `error` (cleared on next successful start)

Crash detection: see §5.2. Same `_health_loop` polls listener count and process liveness on the same 5s cadence.

### 5.2 Listener count

`IcecastManager.get_listener_count() -> int`:
- Endpoint: `http://localhost:{icecast_port}/status-json.xsl` (Icecast2 built-in, no auth required for read)
- Parser: `json.loads(response).get("icestats", {}).get("source", {}).get("listeners", 0)`. When the source field is a list (multi-mount, future slices), pick the entry whose `listenurl` ends with the configured `mount`. When no source is connected, returns 0.
- HTTP timeout: 2s. On timeout/error, return last known value, log warning at most once per minute.

Polling lives in a single background task (`_health_loop`) created at `start()` and cancelled at `stop()`. Cadence: 5s. Same task also calls `engine.is_alive()` and `IcecastManager.is_alive()` for crash detection (§5.1). Writes update `StreamState.listener_count`.

### 5.4 Empty queue / silent stream

On `start()`, the engine begins streaming immediately even when the queue is empty:
- **LiquidsoapEngine**: `mksafe(source)` (already in §4.1 script) emits silence when `request.queue` is empty. Stream stays alive at the icecast mount. Listeners hear silence until a track is queued.
- **FfmpegEngine**: when the asyncio queue is empty, the loop task spawns `ffmpeg -f lavfi -i anullsrc=r={sample_rate}:cl=stereo -t 5 -c:a libmp3lame -b:a {bitrate}k ...` (5-second silence chunks) so the icecast source connection stays open. Once a real track is queued, the next loop iteration picks it up.

Slice 1 does NOT auto-load a track at start — track selection is a Slice 2 concern (agent-driven) or a manual user action via the UI. AC §14 wording reflects this: "VLC plays the stream" means the stream connects and emits audio (silence is valid audio); the queue-and-skip AC verifies actual music playback.

### 5.3 State (Slice 1 only — slim)

```python
@dataclass
class StreamState:
    is_running: bool = False
    engine: str = ""               # "liquidsoap" | "ffmpeg" | ""
    stream_url: str = ""           # full URL incl. mount
    mount: str = "/stream"
    listener_count: int = 0
    current_track: str = ""        # display string "Artist - Title"
    queue: list[str] = field(default_factory=list)
    library_count: int = 0
    error: str = ""
```

Fields for decks, mixer, EFX, spectrum etc. land in later slices on the same singleton — additive only, no rename of Slice 1 fields.

## 6. Icecast2 Configuration

`IcecastManager.configure(config)` writes `/tmp/dj_booth_icecast.xml` from a template. The template matches the spec's XML structure. Slice 1 specifics:

- `<sources>1</sources>` (Slice 3 raises to 2 for deck A/B mounts)
- Single `<mount>` block with mount-name = `/stream`
- `<paths>` uses `/tmp/dj_booth_logs` and `/tmp/dj_booth_icecast.pid` so nothing writes outside `/tmp`
- `<security><chroot>0</chroot></security>` (chroot off — Docker container has no setuid privilege)
- Admin port = `icecast_port` (no separate admin port needed for Slice 1; admin lives at same port behind auth)

The icecast2 binary is launched as `icecast2 -c /tmp/dj_booth_icecast.xml` and detached.

## 7. Library Scan

`LibraryManager.scan(music_dir)`:
- `os.walk` the directory
- Filter by extension: `.mp3 .flac .ogg .oga .m4a .aac .wav .aiff`
- For each file, call `mutagen.File(path, easy=True)` for tags
- Build `Track(path, title, artist, album, genre, year, duration, file_size, format)`
- Slice 1 does NOT compute BPM, key, or waveform peaks (those are Slice 4)
- Store in `self.tracks` (list) and `self.index` (dict by path)

Search: case-insensitive substring match on title/artist/album.

If a file's tags are missing, fall back to filename stem for title and "Unknown Artist" for artist.

## 8. Plugin Files (Slice 1)

```
usr/plugins/dj_booth/
├── plugin.yaml
├── default_config.yaml
├── hooks.py                  # install: apt-get + pip
├── execute.py                # user-triggered start
├── README.md
├── LICENSE
├── api/
│   ├── dj_control.py
│   ├── stream_status.py
│   └── library.py
├── helpers/
│   ├── __init__.py
│   ├── state.py
│   ├── icecast.py
│   ├── engine.py             # Protocol + LiquidsoapEngine + FfmpegEngine
│   └── library.py
├── extensions/
│   └── webui/
│       └── sidebar-quick-actions-main-start/
│           └── dj-button.html
└── webui/
    ├── config.html
    ├── dj-booth.html
    └── dj-store.js
```

No `agents/`, no `tools/`, no `prompts/`, no `extensions/python/system_prompt/` — those arrive in Slice 2.
No `assets/`, `bpm_key.py`, `spectrum.py`, `mic.py` — those arrive in Slices 3–5.

## 9. API Surface (Slice 1)

All routes auto-registered as `POST /api/plugins/dj_booth/<filename>` (`stream_status` overrides to also accept GET).

### `api/dj_control.py`

Single multi-action endpoint:

| `action` | params | effect |
|---|---|---|
| `start` | — | start Icecast2 + engine; populate state |
| `stop` | — | stop both, clear queue |
| `scan_library` | `dir?` (override) | rescan, return count |
| `queue_track` | `path` | append to engine queue |
| `skip` | — | skip current track |
| `clear_queue` | — | drop all queued tracks |

Returns full `StreamState` JSON after every action.

### `api/stream_status.py`

`GET` or `POST`. Returns `StreamState` JSON. Override `get_methods()` to `["GET", "POST"]`.

### `api/library.py`

| `action` | params | returns |
|---|---|---|
| `list` | `page=0`, `per_page=50`, `query=""` | `{tracks: [...], total: int}` |
| `search` | `query` | matching tracks |
| `get_track` | `path` | single track |

## 10. WebUI (Slice 1 — minimal)

### Sidebar button — `extensions/webui/sidebar-quick-actions-main-start/dj-button.html`

Standard A0 sidebar pattern with store gate. Opens `dj-booth.html` modal.

### `webui/dj-store.js`

ES-module Alpine store via `createStore("djBoothStore", ...)`. State + API wrappers. Polls `stream_status` every 1s while modal open. Uses `toastFrontendError/Success/Info` from `/components/notifications/notification-store.js`. No inline error divs.

Methods (Slice 1):
- `init()`, `onOpen()`, `cleanup()`
- `fetchStatus()`, `fetchLibrary(query)`
- `start()`, `stop()`, `scanLibrary()`
- `queueTrack(path)`, `skip()`, `clearQueue()`

### `webui/dj-booth.html`

Single-column layout (the full-screen DJ booth ships in Slice 3):

- **Header**: station name, engine badge (`LIQUIDSOAP` / `FFMPEG (fallback)`), listener count with pulsing dot, stream URL with copy button, Start/Stop button
- **Now Playing**: current track title/artist, large monospace
- **Queue**: ordered list of upcoming tracks; per-row remove button (Slice 3 adds drag-reorder)
- **Library**: search input (debounced 300ms), scrollable list. Each row: title / artist / album / duration / format. Click row = queue. Double-click = queue and skip-to.

Mandatory store gate wrapper:
```html
<div x-data>
  <template x-if="$store.djBoothStore">
    <div x-init="$store.djBoothStore.onOpen()" x-destroy="$store.djBoothStore.cleanup()">
      <!-- content -->
    </div>
  </template>
</div>
```

### `webui/config.html`

Form bound to `config.*`. Fields: `music_dir`, `icecast_port`, `icecast_admin_password`, `icecast_source_password`, `stream_name`, `stream_description`, `stream_genre`, `bitrate` (select 64/128/192/320), `max_listeners`, `public_listing` (checkbox).

Fields not exposed in Slice 1 (deferred): crossfade, auto_dj, mic_*, tts_*, announcement_interval.

## 11. `hooks.py` and `execute.py`

### `hooks.py:install()`

Installs system + Python deps required for Slice 1 only:

```python
apt_packages = ["icecast2", "liquidsoap", "ffmpeg"]
py_packages  = ["mutagen>=1.47", "requests>=2.31"]
```

Aubio, numpy, scipy, pyaudio land in later slices' install hooks (incremental — `install()` is idempotent).

Creates default music dir at `/a0/usr/workdir/music`.

### `execute.py`

User-triggered. Loads config via `helpers.plugins.get_plugin_config("dj_booth")`. Scans library. Starts `IcecastManager`. Selects and starts `StreamEngine`. Prints stream URL. Returns 0 on success, 1 on failure.

## 12. Error Handling

- **Icecast won't bind port**: install/exec aborts, `error="Port {port} in use"`, toast surfaces it, no orphan processes
- **Liquidsoap not installed**: log info, fall back to ffmpeg, badge shows `FFMPEG (fallback)`
- **ffmpeg not installed either**: install/exec aborts with clear error toast and README link
- **Empty library at start**: stream still starts (silence source) and UI shows "Library empty — add files to {music_dir} and click Scan"
- **Crash mid-stream**: 5s health-check task detects, sets `is_running=False`, error toast
- **Telnet connection fails to liquidsoap**: retry 3x with 200ms backoff (covers ~1-2s liquidsoap bind window), then surface as warning toast and mark engine unhealthy (same path as crash mid-stream — see §4.4)
- **Concurrent start/stop**: serialized via `_lifecycle_lock` (§5.1). Idempotent — second start while running is a no-op
- **API error envelope**: handlers return `{"error": "<message>"}` with HTTP 500 on exceptions, `{"error": "<message>", **state}` for handled errors with state. Frontend store reads `data.error` and toasts when present

All user-facing errors via A0 toast notification system. No inline error divs anywhere.

## 13. Manual Test Plan (Slice 1)

Automated test suite arrives Slice 4. Slice 1 ships with documented manual smoke tests:

1. **Install**: fresh A0 Docker container, install plugin via Plugin Hub UI. Verify `hooks.py:install()` exits 0.
2. **Boot**: click Execute. Verify stream URL printed. Verify `pgrep icecast2` and `pgrep liquidsoap` (or `ffmpeg`) return PIDs.
3. **Listen**: open VLC → `http://localhost:8000/stream`. Audio plays (silence acceptable until queue populated).
4. **Library scan**: copy 5 mp3 files into music dir, click Scan in UI, verify 5 tracks shown with tags.
5. **Queue + skip**: queue 3 tracks via UI clicks; verify Now Playing updates, skip mid-track, next plays.
6. **Engine fallback**: rename `liquidsoap` binary, restart plugin, verify `FFMPEG (fallback)` badge and audio still streams.
7. **Listener count**: connect VLC, verify count → 1 within 10s; disconnect, count → 0 within 10s.
8. **Stop**: click Stop. Verify no orphan processes (`pgrep icecast2 liquidsoap ffmpeg` empty), no `/tmp/dj_booth_*.pid` left.
9. **Restart**: Stop → Start → verify clean re-boot.
10. **Public access**: from a second host with port 8000 mapped, connect VLC to `http://<docker-host>:8000/stream`. Audio plays.

## 14. Acceptance Criteria

- [ ] Plugin discovered by Agent Zero (valid `plugin.yaml`, correct directory name)
- [ ] `hooks.py:install()` runs without error on a fresh Docker container
- [ ] `execute.py` starts Icecast2 + selected engine, prints stream URL
- [ ] Icecast2 stream accessible at `http://localhost:8000/stream`
- [ ] VLC plays the stream
- [ ] Liquidsoap engine path works when liquidsoap is installed
- [ ] ffmpeg fallback engine works when liquidsoap is absent
- [ ] Engine selection logged and surfaced as UI badge
- [ ] Library scan finds files, displays tracks with metadata in UI
- [ ] Queue, skip, clear queue all operate via UI and API
- [ ] Listener count updates within 10s of a client connect/disconnect (5s poll + tolerance)
- [ ] Concurrent start POSTs are idempotent — only one icecast/engine pair spawns
- [ ] Stale PIDs from a prior crashed run are cleaned up at start, logged
- [ ] Empty-queue stream emits silence; listener stays connected; UI shows "Library empty" or "Queue empty"
- [ ] Engine failure does not auto-fallback mid-session; user is shown the error and must restart manually
- [ ] Crash detection sets state and toasts within 10s of unexpected process exit
- [ ] Stop leaves no orphan processes and no leftover `/tmp/dj_booth_*.pid` files
- [ ] All errors surface as A0 toast notifications — no inline error divs
- [ ] Settings page saves and loads correctly
- [ ] Plugin uninstalls cleanly (`hooks.py:uninstall()` stops processes)

## 15. Out of Scope (Slice 1 — explicit)

To prevent scope creep during implementation, the following are explicitly OUT of Slice 1:

- Agent `dj_tool`, agent profile, system_prompt extension (Slice 2)
- Two-deck architecture, deck A/B separation (Slice 3)
- Crossfader, mixer, EQ, channel volumes (Slice 3)
- Turntable spinning vinyl SVG, waveform canvases (Slice 3)
- BPM detection, key detection (Slice 4)
- Spectrum analyzer, real-time FFT (Slice 4)
- EFX rack: reverb, delay, filter, flanger (Slice 5)
- Microphone capture, mic mixer (Slice 5)
- Cue points, loop regions, scratch, BPM sync, pitch shift (Slice 5)
- TTS announcements (Slice 2 + 5)
- Track upload via UI (later)
- Auto-DJ scheduling (Slice 2)
- M3U / PLS playlist endpoints (later — Icecast2 may serve these natively)

Each of these gets its own slice's design doc when its time comes.

## 16. Slice Transition Plan

After Slice 1 ships and is verified:

1. Tag git commit `dj_booth/slice-1-complete`
2. Open Slice 2 brainstorming session with this doc + Slice 1 implementation as context
3. Slice 2 adds `tools/dj_tool.py`, `agents/dj/`, `extensions/python/system_prompt/_50_dj_context.py`
4. State singleton extends additively — no Slice 1 field renames

## 17. References

- Source spec: `BUILD_DOCS/A0-SHOUTCAST-SPEC.md`
- Plugin model: `docs/agents/AGENTS.plugins.md`
- Plugin scaffolding skill: `skills/a0-create-plugin/SKILL.md`
- API handler base: `helpers/api.py:ApiHandler`
- Existing example: `usr/plugins/_office/`
