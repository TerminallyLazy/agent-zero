# dj_booth Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working Agent Zero plugin `dj_booth` that runs Icecast2 + a streaming engine (liquidsoap with ffmpeg fallback) so any ICY-compatible client can tune in to a stream sourced from a local music directory. Slice 1 only — no agent tool, no DJ booth UI, no analysis.

**Architecture:** Python async A0 plugin under `usr/plugins/dj_booth/`. Singleton `StreamState`. `IcecastManager` writes XML config and spawns `icecast2`. `StreamEngine` Protocol with `LiquidsoapEngine` (telnet :1234) and `FfmpegEngine` (sequential per-track ffmpeg → icecast) implementations. Engine selected at start via `shutil.which("liquidsoap")`. Single `_health_loop` background task polls listener count + process liveness every 5s. Minimal Alpine-store WebUI: start/stop, library list, queue, now-playing.

**Tech Stack:** Python 3.11+ asyncio, Flask (via A0 ApiHandler), mutagen, icecast2, liquidsoap (apt), ffmpeg (apt), Alpine.js, A0 Plugin framework.

**Spec:** `docs/superpowers/specs/2026-05-03-dj-booth-slice-1-design.md`

---

## File Structure

```
usr/plugins/dj_booth/
├── plugin.yaml                  # manifest
├── default_config.yaml          # bitrate, ports, dirs, defaults
├── hooks.py                     # install/uninstall — apt + pip
├── execute.py                   # user-triggered start
├── README.md                    # listener access + troubleshooting
├── LICENSE                      # MIT
├── api/
│   ├── __init__.py
│   ├── dj_control.py            # multi-action: start/stop/queue/skip/clear/scan
│   ├── stream_status.py         # GET+POST status JSON
│   └── library.py               # list/search/get_track
├── helpers/
│   ├── __init__.py
│   ├── state.py                 # StreamState dataclass + singleton + lock
│   ├── icecast.py               # IcecastManager: xml gen + subprocess + listener poll
│   ├── engine.py                # StreamEngine Protocol + LiquidsoapEngine + FfmpegEngine
│   └── library.py               # LibraryManager + Track + scan + mutagen tags
├── extensions/
│   └── webui/
│       └── sidebar-quick-actions-main-start/
│           └── dj-button.html   # sidebar entry
├── webui/
│   ├── config.html              # plugin settings UI
│   ├── dj-booth.html            # main modal — minimal control panel
│   └── dj-store.js              # Alpine store
└── tests/
    ├── __init__.py
    ├── test_state.py
    ├── test_library.py
    ├── test_icecast.py
    └── test_engine.py
```

Files responsible for one thing each. Process management isolated in `helpers/`. API thin — just dispatch to helpers and return state. WebUI store-only logic — no inline JS in HTML.

---

## Conventions reminder for the implementer

- **Imports**: Always `from usr.plugins.dj_booth.helpers.X import Y` — never `sys.path` hacks. Verified via `usr/plugins/skill_synthesizer/tests/test_skill_synthesizer.py:15`.
- **API handlers**: subclass `helpers.api.ApiHandler`. Override `process(self, input: dict, request: Request) -> dict`. For GET, override `get_methods()`. See `plugins/_browser/api/status.py` for reference.
- **Notifications**: Backend uses `helpers.notification.AgentNotification.add_notification(type, priority, message, title, ...)` (a classmethod-style helper). Frontend imports `toastFrontendError/Success/Info` from `/components/notifications/notification-store.js`. NEVER inline error divs.
- **Frontend**: Mandatory store-gate template with `<template x-if="$store.djBoothStore">`. Store created via `import { createStore } from "/js/AlpineStore.js"`.
- **Subprocess**: Always `asyncio.create_subprocess_exec`, never `subprocess.run` for long-lived processes. Stdout/stderr piped to log files, not inherited.
- **Temp files**: All under `/tmp/dj_booth_*` — no permanent system writes.
- **Tests**: `tests/test_*.py` under plugin root. Use `pytest`. Test imports use full `from usr.plugins.dj_booth.helpers.X import Y` path.

---

## Chunk 1: Scaffolding + state + library

### Task 1: Create plugin scaffold

**Files:**
- Create: `usr/plugins/dj_booth/plugin.yaml`
- Create: `usr/plugins/dj_booth/default_config.yaml`
- Create: `usr/plugins/dj_booth/LICENSE`
- Create: `usr/plugins/dj_booth/api/__init__.py` (empty)
- Create: `usr/plugins/dj_booth/helpers/__init__.py` (empty)
- Create: `usr/plugins/dj_booth/tests/__init__.py` (empty)

- [ ] **Step 1: Write `plugin.yaml`**

```yaml
name: dj_booth
title: DJ Booth
description: >
  Local Icecast2 streaming server with a minimal control panel.
  Compatible with Winamp, VLC, foobar2000, and any ICY-protocol player.
version: 0.1.0
settings_sections:
  - external
per_project_config: false
per_agent_config: false
always_enabled: false
```

- [ ] **Step 2: Write `default_config.yaml`**

```yaml
music_dir: /a0/usr/workdir/music
icecast_port: 8000
icecast_admin_password: hackme
icecast_source_password: sourcepass
stream_name: "Agent Zero Radio"
stream_description: "Powered by Agent Zero"
stream_genre: "Electronic"
stream_url: "http://localhost:8000"
mount: "/stream"
bitrate: 192
sample_rate: 44100
max_listeners: 100
public_listing: false
```

- [ ] **Step 3: Write `LICENSE` (MIT)**

```
MIT License

Copyright (c) 2026 Agent Zero contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```

- [ ] **Step 4: Create empty `__init__.py` files**

```bash
touch usr/plugins/dj_booth/api/__init__.py
touch usr/plugins/dj_booth/helpers/__init__.py
touch usr/plugins/dj_booth/tests/__init__.py
```

- [ ] **Step 5: Verify A0 discovers the plugin**

Restart A0 web server. Open Plugins UI. Verify `DJ Booth` appears in the list. Do NOT enable yet.

- [ ] **Step 6: Commit**

```bash
git add usr/plugins/dj_booth/
git commit -m "feat(dj_booth): scaffold plugin manifest and config"
```

---

### Task 2: StreamState singleton + lifecycle lock

**Files:**
- Create: `usr/plugins/dj_booth/helpers/state.py`
- Test: `usr/plugins/dj_booth/tests/test_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state.py
import asyncio
import pytest
from usr.plugins.dj_booth.helpers.state import (
    StreamState, get_state, get_lifecycle_lock, reset_state,
)


def test_get_state_returns_singleton():
    s1 = get_state()
    s2 = get_state()
    assert s1 is s2


def test_default_state_values():
    reset_state()
    s = get_state()
    assert s.is_running is False
    assert s.engine == ""
    assert s.listener_count == 0
    assert s.queue == []
    assert s.error == ""


def test_lifecycle_lock_is_singleton():
    l1 = get_lifecycle_lock()
    l2 = get_lifecycle_lock()
    assert l1 is l2
    assert isinstance(l1, asyncio.Lock)


def test_reset_state_clears_runtime_fields_keeps_library_count():
    reset_state()
    s = get_state()
    s.is_running = True
    s.listener_count = 5
    s.library_count = 42
    s.error = "old"
    reset_state(keep_library=True, keep_error=False)
    s = get_state()
    assert s.is_running is False
    assert s.listener_count == 0
    assert s.library_count == 42
    assert s.error == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/lazy/Desktop/agent-zero
python -m pytest usr/plugins/dj_booth/tests/test_state.py -v
```
Expected: ImportError / ModuleNotFoundError on `usr.plugins.dj_booth.helpers.state`

- [ ] **Step 3: Write `helpers/state.py`**

```python
"""Singleton stream state for the dj_booth plugin (Slice 1)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StreamState:
    is_running: bool = False
    engine: str = ""              # "liquidsoap" | "ffmpeg" | ""
    stream_url: str = ""          # full URL incl. mount
    mount: str = "/stream"
    listener_count: int = 0
    current_track: str = ""       # display string, e.g. "Artist - Title"
    queue: list[str] = field(default_factory=list)
    library_count: int = 0
    error: str = ""
    icecast_pid: int = 0
    engine_pid: int = 0


_instance: Optional[StreamState] = None
_lock: Optional[asyncio.Lock] = None


def get_state() -> StreamState:
    global _instance
    if _instance is None:
        _instance = StreamState()
    return _instance


def get_lifecycle_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def reset_state(keep_library: bool = True, keep_error: bool = False) -> None:
    """Reset to defaults. Used after stop() and at module reload."""
    s = get_state()
    library_count = s.library_count if keep_library else 0
    error = s.error if keep_error else ""
    fresh = StreamState()
    fresh.library_count = library_count
    fresh.error = error
    # in-place replace fields so other holders of the singleton see updates
    for f in fresh.__dataclass_fields__:
        setattr(s, f, getattr(fresh, f))
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_state.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add usr/plugins/dj_booth/helpers/state.py usr/plugins/dj_booth/tests/test_state.py
git commit -m "feat(dj_booth): add StreamState singleton and lifecycle lock"
```

---

### Task 3: LibraryManager + Track + scan

**Files:**
- Create: `usr/plugins/dj_booth/helpers/library.py`
- Test: `usr/plugins/dj_booth/tests/test_library.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_library.py
import os
import tempfile
from pathlib import Path
import pytest
from usr.plugins.dj_booth.helpers.library import LibraryManager, Track


def make_dummy_audio(path: Path, content: bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00"):
    path.write_bytes(content + b"\x00" * 1024)


@pytest.fixture
def music_dir():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        make_dummy_audio(root / "song1.mp3")
        make_dummy_audio(root / "song2.flac")
        (root / "subdir").mkdir()
        make_dummy_audio(root / "subdir" / "nested.mp3")
        (root / "ignore.txt").write_text("not audio")
        (root / "broken.mp3").write_bytes(b"")  # zero-byte
        yield str(root)


def test_scan_finds_audio_files(music_dir):
    lib = LibraryManager()
    lib.scan(music_dir)
    paths = sorted(t.path for t in lib.tracks)
    assert any(p.endswith("song1.mp3") for p in paths)
    assert any(p.endswith("song2.flac") for p in paths)
    assert any(p.endswith("nested.mp3") for p in paths)
    assert not any(p.endswith("ignore.txt") for p in paths)


def test_scan_falls_back_to_filename_when_tags_missing(music_dir):
    lib = LibraryManager()
    lib.scan(music_dir)
    t = next(t for t in lib.tracks if t.path.endswith("song1.mp3"))
    assert t.title  # at minimum the filename stem
    assert t.artist  # at minimum "Unknown Artist"


def test_search_case_insensitive(music_dir):
    lib = LibraryManager()
    lib.scan(music_dir)
    results = lib.search("SONG")
    assert len(results) >= 2


def test_get_track_by_path(music_dir):
    lib = LibraryManager()
    lib.scan(music_dir)
    p = lib.tracks[0].path
    assert lib.get_track(p) is not None
    assert lib.get_track("/does/not/exist") is None


def test_scan_handles_unreadable_file_gracefully(music_dir):
    lib = LibraryManager()
    # broken.mp3 is zero-byte — should be skipped or get default fields, not crash
    lib.scan(music_dir)  # must not raise


def test_scan_returns_count(music_dir):
    lib = LibraryManager()
    count = lib.scan(music_dir)
    assert count == len(lib.tracks)
```

- [ ] **Step 2: Run test, verify failure**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_library.py -v
```
Expected: ImportError.

- [ ] **Step 3: Write `helpers/library.py`**

```python
"""Music library scanner using mutagen for tag extraction."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".wav", ".aiff", ".aif"}


@dataclass
class Track:
    path: str
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    year: str = ""
    duration: float = 0.0
    file_size: int = 0
    format: str = ""


class LibraryManager:
    """Scans a directory and exposes tracks. Not a singleton — kept on the plugin runtime."""

    def __init__(self):
        self.tracks: list[Track] = []
        self.index: dict[str, Track] = {}
        self.last_dir: str = ""

    def scan(self, music_dir: str) -> int:
        self.tracks.clear()
        self.index.clear()
        self.last_dir = music_dir
        if not os.path.isdir(music_dir):
            return 0
        for root, _dirs, files in os.walk(music_dir):
            for name in files:
                p = Path(root) / name
                if p.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue
                track = self._read_track(str(p))
                if track is not None:
                    self.tracks.append(track)
                    self.index[track.path] = track
        return len(self.tracks)

    def _read_track(self, path: str) -> Optional[Track]:
        try:
            stem = Path(path).stem
            ext = Path(path).suffix.lower().lstrip(".")
            size = os.path.getsize(path)
            track = Track(
                path=path,
                title=stem,
                artist="Unknown Artist",
                file_size=size,
                format=ext,
            )
            try:
                import mutagen
                meta = mutagen.File(path, easy=True)
                if meta is not None:
                    if meta.tags:
                        track.title = (meta.tags.get("title", [stem])[0] or stem)
                        track.artist = (meta.tags.get("artist", ["Unknown Artist"])[0] or "Unknown Artist")
                        track.album = (meta.tags.get("album", [""])[0] or "")
                        track.genre = (meta.tags.get("genre", [""])[0] or "")
                        track.year = (meta.tags.get("date", [""])[0] or "")
                    if meta.info is not None:
                        track.duration = float(getattr(meta.info, "length", 0.0))
            except Exception:
                pass  # tags optional — fallbacks already populated
            return track
        except OSError:
            return None

    def search(self, query: str) -> list[Track]:
        q = query.lower()
        return [
            t for t in self.tracks
            if q in t.title.lower()
            or q in t.artist.lower()
            or q in t.album.lower()
            or q in t.genre.lower()
        ]

    def get_track(self, path: str) -> Optional[Track]:
        return self.index.get(path)
```

- [ ] **Step 4: Install mutagen for the test environment if needed**

```bash
pip install 'mutagen>=1.47'
```

- [ ] **Step 5: Run tests, verify pass**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_library.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add usr/plugins/dj_booth/helpers/library.py usr/plugins/dj_booth/tests/test_library.py
git commit -m "feat(dj_booth): add LibraryManager with mutagen tag scan"
```

---

## Chunk 2: Icecast manager + Engine implementations

### Task 4: IcecastManager (config gen + spawn + listener poll)

**Files:**
- Create: `usr/plugins/dj_booth/helpers/icecast.py`
- Test: `usr/plugins/dj_booth/tests/test_icecast.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_icecast.py
import os
import re
import pytest
from usr.plugins.dj_booth.helpers.icecast import (
    IcecastManager, render_icecast_xml,
)


def test_render_xml_substitutes_all_fields():
    cfg = {
        "icecast_port": 8000,
        "icecast_admin_password": "adminpw",
        "icecast_source_password": "sourcepw",
        "stream_name": "TestRadio",
        "stream_description": "desc",
        "stream_genre": "Test",
        "stream_url": "http://localhost:8000",
        "mount": "/stream",
        "max_listeners": 50,
        "public_listing": False,
    }
    xml = render_icecast_xml(cfg)
    assert "<port>8000</port>" in xml
    assert "<source-password>sourcepw</source-password>" in xml
    assert "<admin-password>adminpw</admin-password>" in xml
    assert "<mount-name>/stream</mount-name>" in xml
    assert "<max-listeners>50</max-listeners>" in xml
    assert "<public>0</public>" in xml
    # /tmp paths only
    assert "/tmp/dj_booth_logs" in xml
    assert "/tmp/dj_booth_icecast.pid" in xml


def test_render_xml_public_listing_true():
    cfg = {"icecast_port": 8000, "icecast_admin_password": "a",
           "icecast_source_password": "s", "stream_name": "n",
           "stream_description": "d", "stream_genre": "g",
           "stream_url": "u", "mount": "/m", "max_listeners": 1,
           "public_listing": True}
    xml = render_icecast_xml(cfg)
    assert "<public>1</public>" in xml


def test_parse_listener_count_from_status_json():
    sample = '{"icestats":{"source":{"listenurl":"http://localhost:8000/stream","listeners":7}}}'
    assert IcecastManager.parse_listener_count(sample, "/stream") == 7


def test_parse_listener_count_multi_mount():
    sample = '''{"icestats":{"source":[
        {"listenurl":"http://x/stream","listeners":3},
        {"listenurl":"http://x/other","listeners":99}
    ]}}'''
    assert IcecastManager.parse_listener_count(sample, "/stream") == 3


def test_parse_listener_count_no_source():
    assert IcecastManager.parse_listener_count('{"icestats":{}}', "/stream") == 0


def test_parse_listener_count_malformed():
    assert IcecastManager.parse_listener_count("not json", "/stream") == 0


def test_get_singleton():
    m1 = IcecastManager.get()
    m2 = IcecastManager.get()
    assert m1 is m2
```

- [ ] **Step 2: Run, verify failure**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_icecast.py -v
```

- [ ] **Step 3: Write `helpers/icecast.py`**

```python
"""Icecast2 process manager: writes config, spawns icecast2, polls listener count."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from pathlib import Path
from typing import Optional

import urllib.request
import urllib.error


log = logging.getLogger(__name__)


ICECAST_XML_TEMPLATE = """<icecast>
  <location>localhost</location>
  <admin>admin@localhost</admin>
  <limits>
    <clients>{max_listeners}</clients>
    <sources>2</sources>
    <queue-size>524288</queue-size>
    <client-timeout>30</client-timeout>
    <header-timeout>15</header-timeout>
    <source-timeout>10</source-timeout>
  </limits>
  <authentication>
    <source-password>{source_password}</source-password>
    <relay-password>{relay_password}</relay-password>
    <admin-user>admin</admin-user>
    <admin-password>{admin_password}</admin-password>
  </authentication>
  <hostname>localhost</hostname>
  <listen-socket>
    <port>{port}</port>
  </listen-socket>
  <mount>
    <mount-name>{mount}</mount-name>
    <max-listeners>{max_listeners}</max-listeners>
    <stream-name>{stream_name}</stream-name>
    <stream-description>{stream_description}</stream-description>
    <stream-url>{stream_url}</stream-url>
    <genre>{stream_genre}</genre>
    <public>{public_int}</public>
  </mount>
  <fileserve>1</fileserve>
  <paths>
    <basedir>/usr/share/icecast2</basedir>
    <logdir>/tmp/dj_booth_logs</logdir>
    <webroot>/usr/share/icecast2/web</webroot>
    <adminroot>/usr/share/icecast2/admin</adminroot>
    <pidfile>/tmp/dj_booth_icecast.pid</pidfile>
  </paths>
  <logging>
    <accesslog>access.log</accesslog>
    <errorlog>error.log</errorlog>
    <loglevel>3</loglevel>
  </logging>
  <security>
    <chroot>0</chroot>
  </security>
</icecast>
"""

XML_CONFIG_PATH = "/tmp/dj_booth_icecast.xml"
PIDFILE = "/tmp/dj_booth_icecast.pid"
LOG_DIR = "/tmp/dj_booth_logs"


def render_icecast_xml(cfg: dict) -> str:
    return ICECAST_XML_TEMPLATE.format(
        max_listeners=int(cfg.get("max_listeners", 100)),
        source_password=cfg["icecast_source_password"],
        relay_password=cfg.get("icecast_relay_password", cfg["icecast_admin_password"]),
        admin_password=cfg["icecast_admin_password"],
        port=int(cfg["icecast_port"]),
        mount=cfg.get("mount", "/stream"),
        stream_name=cfg.get("stream_name", "Stream"),
        stream_description=cfg.get("stream_description", ""),
        stream_url=cfg.get("stream_url", ""),
        stream_genre=cfg.get("stream_genre", ""),
        public_int=1 if cfg.get("public_listing") else 0,
    )


class IcecastManager:
    _instance: Optional["IcecastManager"] = None

    @classmethod
    def get(cls) -> "IcecastManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.config: dict = {}

    async def start(self, config: dict) -> None:
        self.config = config
        os.makedirs(LOG_DIR, exist_ok=True)
        Path(XML_CONFIG_PATH).write_text(render_icecast_xml(config))
        log.info("dj_booth: starting icecast2 with %s", XML_CONFIG_PATH)
        self.process = await asyncio.create_subprocess_exec(
            "icecast2", "-c", XML_CONFIG_PATH,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # icecast needs ~200ms to bind
        await asyncio.sleep(0.5)
        if self.process.returncode is not None:
            raise RuntimeError(f"icecast2 exited immediately, code {self.process.returncode}")

    async def stop(self) -> None:
        if self.process is None:
            return
        try:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        except ProcessLookupError:
            pass
        self.process = None
        for path in (XML_CONFIG_PATH, PIDFILE):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    async def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def get_listener_count(self) -> int:
        port = int(self.config.get("icecast_port", 8000))
        mount = self.config.get("mount", "/stream")
        url = f"http://localhost:{port}/status-json.xsl"
        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(url, timeout=2).read().decode("utf-8")
            )
        except (urllib.error.URLError, OSError):
            return 0
        return self.parse_listener_count(text, mount)

    @staticmethod
    def parse_listener_count(text: str, mount: str) -> int:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return 0
        source = data.get("icestats", {}).get("source")
        if source is None:
            return 0
        if isinstance(source, list):
            for entry in source:
                if isinstance(entry, dict) and entry.get("listenurl", "").endswith(mount):
                    return int(entry.get("listeners", 0))
            return 0
        if isinstance(source, dict):
            return int(source.get("listeners", 0))
        return 0
```

- [ ] **Step 4: Run, verify pass**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_icecast.py -v
```

- [ ] **Step 5: Commit**

```bash
git add usr/plugins/dj_booth/helpers/icecast.py usr/plugins/dj_booth/tests/test_icecast.py
git commit -m "feat(dj_booth): add IcecastManager with xml gen and listener polling"
```

---

### Task 5: StreamEngine Protocol + FfmpegEngine

**Files:**
- Create: `usr/plugins/dj_booth/helpers/engine.py`
- Test: `usr/plugins/dj_booth/tests/test_engine.py`

We split the engine work into two tasks: this one defines the Protocol and ships the FfmpegEngine fallback (simpler, no telnet). Task 6 adds LiquidsoapEngine.

- [ ] **Step 1: Write tests for engine selection + FfmpegEngine**

```python
# tests/test_engine.py
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
```

(Mark `pytest_plugins = ["pytest_asyncio"]` in `tests/__init__.py` or use `pytest-asyncio` mode auto. Add `pip install pytest-asyncio` if not already.)

- [ ] **Step 2: Run, verify failure**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_engine.py -v
```

- [ ] **Step 3: Write `helpers/engine.py` (Protocol + FfmpegEngine + select_engine)**

```python
"""StreamEngine: protocol + FfmpegEngine (fallback) + LiquidsoapEngine (preferred).

Engine selection is one-shot at start() — no mid-session auto-swap.
See spec §4.4 for failure semantics.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Optional, Protocol


log = logging.getLogger(__name__)


class StreamEngine(Protocol):
    name: str
    async def start(self, config: dict, initial_tracks: list[str]) -> None: ...
    async def stop(self) -> None: ...
    async def queue_track(self, path: str) -> None: ...
    async def skip(self) -> None: ...
    async def clear_queue(self) -> None: ...
    async def is_alive(self) -> bool: ...
    async def get_current(self) -> Optional[str]: ...


def select_engine() -> StreamEngine:
    if shutil.which("liquidsoap"):
        return LiquidsoapEngine()
    if shutil.which("ffmpeg"):
        return FfmpegEngine()
    raise RuntimeError("dj_booth: neither liquidsoap nor ffmpeg is installed")


class FfmpegEngine:
    """
    Fallback engine. Maintains an asyncio queue of track paths and spawns
    one ffmpeg per track that streams directly to the icecast source.
    No crossfade. Brief silence between tracks is expected.
    """
    name = "ffmpeg"

    def __init__(self):
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.config: dict = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._current_proc: Optional[asyncio.subprocess.Process] = None
        self._current_path: str = ""
        self._failure_streak: int = 0

    async def start(self, config: dict, initial_tracks: list[str]) -> None:
        self.config = config
        for t in initial_tracks:
            await self.queue.put(t)
        self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        await self._kill_current()
        # drain queue
        while not self.queue.empty():
            self.queue.get_nowait()

    async def queue_track(self, path: str) -> None:
        await self.queue.put(path)

    async def skip(self) -> None:
        await self._kill_current()

    async def clear_queue(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()

    async def is_alive(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    async def get_current(self) -> Optional[str]:
        return self._current_path or None

    async def _kill_current(self) -> None:
        if self._current_proc and self._current_proc.returncode is None:
            try:
                self._current_proc.terminate()
                try:
                    await asyncio.wait_for(self._current_proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self._current_proc.kill()
                    await self._current_proc.wait()
            except ProcessLookupError:
                pass
        self._current_proc = None
        self._current_path = ""

    async def _loop(self) -> None:
        cfg = self.config
        port = int(cfg.get("icecast_port", 8000))
        bitrate = int(cfg.get("bitrate", 192))
        sample_rate = int(cfg.get("sample_rate", 44100))
        mount = cfg.get("mount", "/stream")
        password = cfg["icecast_source_password"]
        icecast_url = f"icecast://source:{password}@localhost:{port}{mount}"

        while True:
            try:
                path: str
                try:
                    path = self.queue.get_nowait()
                    self._current_path = path
                    cmd = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-re", "-i", path,
                        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
                        "-ar", str(sample_rate), "-ac", "2",
                        "-content_type", "audio/mpeg", "-f", "mp3",
                        icecast_url,
                    ]
                except asyncio.QueueEmpty:
                    self._current_path = ""
                    # silence chunk to keep source connection alive
                    cmd = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-re", "-f", "lavfi",
                        "-i", f"anullsrc=r={sample_rate}:cl=stereo",
                        "-t", "5",
                        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
                        "-content_type", "audio/mpeg", "-f", "mp3",
                        icecast_url,
                    ]
                self._current_proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                rc = await self._current_proc.wait()
                if rc != 0 and self._current_path:
                    self._failure_streak += 1
                    log.warning("dj_booth ffmpeg failed for %s rc=%d", self._current_path, rc)
                    if self._failure_streak >= 3:
                        log.error("dj_booth ffmpeg engine: 3 consecutive failures, exiting loop")
                        return
                else:
                    self._failure_streak = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("dj_booth ffmpeg loop error")
                await asyncio.sleep(0.5)


class LiquidsoapEngine:
    """Placeholder — full impl in Task 6."""
    name = "liquidsoap"
    async def start(self, config: dict, initial_tracks: list[str]) -> None:
        raise NotImplementedError("Task 6")
    async def stop(self) -> None: pass
    async def queue_track(self, path: str) -> None: pass
    async def skip(self) -> None: pass
    async def clear_queue(self) -> None: pass
    async def is_alive(self) -> bool: return False
    async def get_current(self) -> Optional[str]: return None
```

- [ ] **Step 4: Configure pytest-asyncio**

Add to `usr/plugins/dj_booth/tests/conftest.py`:

```python
import pytest
pytest_plugins = ["pytest_asyncio"]
```

Or set `asyncio_mode = "auto"` in a `usr/plugins/dj_booth/pytest.ini` if preferred.

Install:
```bash
pip install pytest-asyncio
```

- [ ] **Step 5: Run, verify pass**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_engine.py -v
```

- [ ] **Step 6: Commit**

```bash
git add usr/plugins/dj_booth/helpers/engine.py usr/plugins/dj_booth/tests/test_engine.py usr/plugins/dj_booth/tests/conftest.py
git commit -m "feat(dj_booth): add StreamEngine protocol and FfmpegEngine fallback"
```

---

### Task 6: LiquidsoapEngine — telnet control + .liq generation

**Files:**
- Modify: `usr/plugins/dj_booth/helpers/engine.py` (replace LiquidsoapEngine class)
- Modify: `usr/plugins/dj_booth/tests/test_engine.py` (add LiquidsoapEngine telnet tests)

- [ ] **Step 1: Write failing tests for LiquidsoapEngine**

Append to `tests/test_engine.py`:

```python
from usr.plugins.dj_booth.helpers.engine import LiquidsoapEngine, render_liq_script


def test_render_liq_script_has_required_sections():
    cfg = {
        "icecast_port": 8000, "icecast_source_password": "pw",
        "stream_name": "n", "stream_description": "d", "stream_genre": "g",
        "stream_url": "u", "mount": "/stream", "bitrate": 192,
        "public_listing": False,
    }
    script = render_liq_script(cfg)
    assert 'set("server.telnet", true)' in script
    assert 'set("server.telnet.port", 1234)' in script
    assert 'request.queue(id="main")' in script
    assert "output.icecast" in script
    assert 'mount="/stream"' in script
    assert "%mp3(bitrate=192)" in script
    assert "mksafe" in script


@pytest.mark.asyncio
async def test_liquidsoap_engine_telnet_round_trip(monkeypatch):
    """Stub the telnet send to confirm command formatting."""
    eng = LiquidsoapEngine()
    sent = []

    async def fake_send(cmd: str) -> str:
        sent.append(cmd)
        if cmd.startswith("main.push"):
            return "1"
        if cmd == "request.on_air":
            return "1"
        if cmd.startswith("request.metadata"):
            return 'title="X"\nartist="Y"'
        return "OK"

    monkeypatch.setattr(eng, "_telnet_send", fake_send)

    await eng.queue_track("/m/a.mp3")
    assert sent[-1] == "main.push /m/a.mp3"

    await eng.skip()
    assert sent[-1] == "main.skip"

    current = await eng.get_current()
    assert current and "Y" in current and "X" in current
```

- [ ] **Step 2: Run, verify failure**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_engine.py -v
```

- [ ] **Step 3: Replace LiquidsoapEngine in `helpers/engine.py`**

Add at top with other constants:

```python
LIQ_TELNET_HOST = "localhost"
LIQ_TELNET_PORT = 1234
LIQ_SCRIPT_PATH = "/tmp/dj_booth.liq"


LIQ_SCRIPT_TEMPLATE = '''# dj_booth — generated, do not edit
set("server.telnet", true)
set("server.telnet.port", {telnet_port})
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
'''


def render_liq_script(cfg: dict) -> str:
    return LIQ_SCRIPT_TEMPLATE.format(
        telnet_port=LIQ_TELNET_PORT,
        bitrate=int(cfg.get("bitrate", 192)),
        icecast_port=int(cfg["icecast_port"]),
        source_password=cfg["icecast_source_password"],
        mount=cfg.get("mount", "/stream"),
        stream_name=cfg.get("stream_name", "Stream"),
        stream_description=cfg.get("stream_description", ""),
        stream_genre=cfg.get("stream_genre", ""),
        stream_url=cfg.get("stream_url", ""),
        public_int="true" if cfg.get("public_listing") else "false",
    )
```

Replace the placeholder `LiquidsoapEngine` with:

```python
class LiquidsoapEngine:
    name = "liquidsoap"

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.config: dict = {}

    async def start(self, config: dict, initial_tracks: list[str]) -> None:
        self.config = config
        from pathlib import Path as _P
        _P(LIQ_SCRIPT_PATH).write_text(render_liq_script(config))
        self.process = await asyncio.create_subprocess_exec(
            "liquidsoap", LIQ_SCRIPT_PATH,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # liquidsoap takes ~1-2s to bind telnet port — retry
        last_err: Optional[Exception] = None
        for _ in range(15):
            await asyncio.sleep(0.2)
            if self.process.returncode is not None:
                raise RuntimeError(f"liquidsoap exited rc={self.process.returncode}")
            try:
                await self._telnet_send("version")
                last_err = None
                break
            except (ConnectionRefusedError, OSError) as e:
                last_err = e
        if last_err is not None:
            await self.stop()
            raise RuntimeError(f"liquidsoap telnet failed: {last_err}")
        for path in initial_tracks:
            await self.queue_track(path)

    async def stop(self) -> None:
        if self.process is None:
            return
        try:
            try:
                await asyncio.wait_for(self._telnet_send("quit"), timeout=1.0)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
        except ProcessLookupError:
            pass
        self.process = None
        try:
            import os as _os
            _os.unlink(LIQ_SCRIPT_PATH)
        except FileNotFoundError:
            pass

    async def queue_track(self, path: str) -> None:
        await self._telnet_send(f"main.push {path}")

    async def skip(self) -> None:
        await self._telnet_send("main.skip")

    async def clear_queue(self) -> None:
        # Liquidsoap has no built-in queue purge; skip until empty.
        # Slice 1: cap at 100 skips defensively.
        for _ in range(100):
            resp = await self._telnet_send("main.length")
            try:
                if int(resp.strip()) == 0:
                    return
            except ValueError:
                return
            await self._telnet_send("main.skip")

    async def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def get_current(self) -> Optional[str]:
        try:
            rid = (await self._telnet_send("request.on_air")).strip()
            if not rid or rid == "":
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

    async def _telnet_send(self, command: str) -> str:
        reader, writer = await asyncio.open_connection(LIQ_TELNET_HOST, LIQ_TELNET_PORT)
        try:
            writer.write((command + "\n").encode())
            await writer.drain()
            buf = b""
            while True:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=2.0)
                if not chunk:
                    break
                buf += chunk
                if b"END\r\n" in buf or b"END\n" in buf:
                    break
            text = buf.decode(errors="replace")
            # Strip trailing END marker
            for marker in ("END\r\n", "END\n"):
                if text.endswith(marker):
                    text = text[: -len(marker)]
                    break
            return text
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
```

- [ ] **Step 4: Run all engine tests, verify pass**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_engine.py -v
```

- [ ] **Step 5: Commit**

```bash
git add usr/plugins/dj_booth/helpers/engine.py usr/plugins/dj_booth/tests/test_engine.py
git commit -m "feat(dj_booth): implement LiquidsoapEngine with telnet control"
```

---

## Chunk 3: Lifecycle orchestrator + API handlers + hooks/execute

### Task 7: Lifecycle orchestrator (start_stack/stop_stack)

**Files:**
- Create: `usr/plugins/dj_booth/helpers/lifecycle.py`
- Test: `usr/plugins/dj_booth/tests/test_lifecycle.py`

This is the glue: pre-start checks (stale PID, port probe, config validation) + spawn order + health loop + clean stop. Lives separately from `IcecastManager` and `engine.py` because it owns state mutations.

- [ ] **Step 1: Write tests**

```python
# tests/test_lifecycle.py
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from usr.plugins.dj_booth.helpers import lifecycle, state


@pytest.mark.asyncio
async def test_start_stack_idempotent(monkeypatch):
    state.reset_state()
    s = state.get_state()
    s.is_running = True

    fake_ice = AsyncMock()
    fake_eng = AsyncMock()
    fake_eng.name = "ffmpeg"
    monkeypatch.setattr(lifecycle, "_get_icecast", lambda: fake_ice)
    monkeypatch.setattr(lifecycle, "_make_engine", lambda: fake_eng)

    await lifecycle.start_stack({"icecast_port": 8000})
    fake_ice.start.assert_not_called()


@pytest.mark.asyncio
async def test_start_stack_aborts_on_port_busy(monkeypatch):
    state.reset_state()

    def fake_bind_probe(port: int) -> None:
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(lifecycle, "_port_bind_probe", fake_bind_probe)

    with pytest.raises(RuntimeError, match="in use"):
        await lifecycle.start_stack({"icecast_port": 8000, "icecast_source_password": "x",
                                     "icecast_admin_password": "x", "music_dir": "/tmp"})

    s = state.get_state()
    assert s.is_running is False
    assert "in use" in s.error.lower()


@pytest.mark.asyncio
async def test_validate_config_required_fields():
    with pytest.raises(ValueError, match="icecast_port"):
        lifecycle.validate_config({})
    with pytest.raises(ValueError, match="icecast_source_password"):
        lifecycle.validate_config({"icecast_port": 8000})
    # valid passes
    lifecycle.validate_config({
        "icecast_port": 8000, "icecast_source_password": "x",
        "icecast_admin_password": "x", "music_dir": "/tmp",
    })
```

- [ ] **Step 2: Run, verify failure**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_lifecycle.py -v
```

- [ ] **Step 3: Write `helpers/lifecycle.py`**

```python
"""Lifecycle orchestration: start_stack, stop_stack, _health_loop."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from pathlib import Path
from typing import Optional

from usr.plugins.dj_booth.helpers import state as _state
from usr.plugins.dj_booth.helpers.icecast import IcecastManager, PIDFILE as ICECAST_PIDFILE
from usr.plugins.dj_booth.helpers.engine import (
    StreamEngine, select_engine, LIQ_SCRIPT_PATH,
)


log = logging.getLogger(__name__)


REQUIRED_FIELDS = (
    "icecast_port", "icecast_source_password", "icecast_admin_password", "music_dir",
)

PIDFILES_TO_SWEEP = (
    ICECAST_PIDFILE,
)

_engine: Optional[StreamEngine] = None
_health_task: Optional[asyncio.Task] = None


def _get_icecast() -> IcecastManager:
    return IcecastManager.get()


def _make_engine() -> StreamEngine:
    return select_engine()


def validate_config(cfg: dict) -> None:
    for f in REQUIRED_FIELDS:
        if f not in cfg or cfg[f] in (None, ""):
            raise ValueError(f"dj_booth config missing required field: {f}")
    try:
        port = int(cfg["icecast_port"])
    except (TypeError, ValueError):
        raise ValueError("icecast_port must be an integer")
    if not (1 <= port <= 65535):
        raise ValueError(f"icecast_port {port} out of range")


def _port_bind_probe(port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
    finally:
        s.close()


def _sweep_stale_pidfiles() -> None:
    for path in PIDFILES_TO_SWEEP:
        try:
            content = Path(path).read_text().strip()
            pid = int(content)
        except (FileNotFoundError, ValueError):
            try:
                Path(path).unlink()
            except FileNotFoundError:
                pass
            continue
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGTERM)
            log.info("dj_booth: cleaned up stale pid %d from %s", pid, path)
        except ProcessLookupError:
            pass
        except PermissionError:
            log.warning("dj_booth: pid %d from %s not killable", pid, path)
        try:
            Path(path).unlink()
        except FileNotFoundError:
            pass


async def start_stack(cfg: dict, initial_tracks: Optional[list[str]] = None) -> None:
    global _engine, _health_task
    s = _state.get_state()
    lock = _state.get_lifecycle_lock()
    async with lock:
        if s.is_running:
            log.info("dj_booth: start requested but already running — no-op")
            return
        try:
            validate_config(cfg)
            _sweep_stale_pidfiles()
            _port_bind_probe(int(cfg["icecast_port"]))
        except (ValueError, OSError) as e:
            s.error = str(e) if isinstance(e, ValueError) else f"Port {cfg.get('icecast_port')} in use"
            s.is_running = False
            raise RuntimeError(s.error) from e

        ice = _get_icecast()
        await ice.start(cfg)

        _engine = _make_engine()
        try:
            await _engine.start(cfg, initial_tracks or [])
        except Exception as e:
            s.error = f"engine start failed: {e}"
            await ice.stop()
            _engine = None
            s.is_running = False
            raise

        s.is_running = True
        s.error = ""
        s.engine = _engine.name
        s.mount = cfg.get("mount", "/stream")
        s.stream_url = f"http://localhost:{cfg['icecast_port']}{s.mount}"
        s.icecast_pid = ice.process.pid if ice.process else 0

        _health_task = asyncio.create_task(_health_loop(cfg))


async def stop_stack() -> None:
    global _engine, _health_task
    s = _state.get_state()
    lock = _state.get_lifecycle_lock()
    async with lock:
        if _health_task:
            _health_task.cancel()
            try:
                await _health_task
            except asyncio.CancelledError:
                pass
            _health_task = None
        if _engine is not None:
            try:
                await _engine.stop()
            except Exception:
                log.exception("dj_booth: engine stop error")
            _engine = None
        try:
            await IcecastManager.get().stop()
        except Exception:
            log.exception("dj_booth: icecast stop error")
        _state.reset_state(keep_library=True, keep_error=False)


async def queue_track(path: str) -> None:
    s = _state.get_state()
    if not s.is_running or _engine is None:
        raise RuntimeError("stream not running")
    await _engine.queue_track(path)
    s.queue.append(path)


async def skip_current() -> None:
    if _engine is None:
        raise RuntimeError("stream not running")
    await _engine.skip()


async def clear_queue() -> None:
    s = _state.get_state()
    if _engine is None:
        return
    await _engine.clear_queue()
    s.queue.clear()


async def _health_loop(cfg: dict) -> None:
    s = _state.get_state()
    ice = IcecastManager.get()
    while True:
        try:
            await asyncio.sleep(5.0)
            if not await ice.is_alive():
                s.error = "icecast died"
                s.is_running = False
                log.error("dj_booth: icecast died — health loop exiting")
                return
            if _engine is not None and not await _engine.is_alive():
                s.error = "engine died"
                s.is_running = False
                log.error("dj_booth: engine died — health loop exiting")
                return
            s.listener_count = await ice.get_listener_count()
            if _engine is not None:
                cur = await _engine.get_current()
                if cur:
                    s.current_track = cur
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("dj_booth: health loop error")
```

- [ ] **Step 4: Run, verify pass**

```bash
python -m pytest usr/plugins/dj_booth/tests/test_lifecycle.py -v
```

- [ ] **Step 5: Commit**

```bash
git add usr/plugins/dj_booth/helpers/lifecycle.py usr/plugins/dj_booth/tests/test_lifecycle.py
git commit -m "feat(dj_booth): add lifecycle orchestrator with health loop"
```

---

### Task 8: API handlers — dj_control, stream_status, library

**Files:**
- Create: `usr/plugins/dj_booth/api/dj_control.py`
- Create: `usr/plugins/dj_booth/api/stream_status.py`
- Create: `usr/plugins/dj_booth/api/library.py`

API handlers are thin: parse, dispatch to helpers, return state. No business logic here.

- [ ] **Step 1: Write `api/stream_status.py`**

```python
from dataclasses import asdict
from helpers.api import ApiHandler, Request

from usr.plugins.dj_booth.helpers.state import get_state


class StreamStatus(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict:
        return asdict(get_state())
```

- [ ] **Step 2: Write `api/dj_control.py`**

```python
from dataclasses import asdict
from helpers.api import ApiHandler, Request

from usr.plugins.dj_booth.helpers import lifecycle
from usr.plugins.dj_booth.helpers.library import LibraryManager
from usr.plugins.dj_booth.helpers.state import get_state
from helpers.plugins import get_plugin_config


_library: LibraryManager | None = None


def _get_library() -> LibraryManager:
    global _library
    if _library is None:
        _library = LibraryManager()
    return _library


class DjControl(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        action = (input or {}).get("action", "")
        cfg = get_plugin_config("dj_booth") or {}
        try:
            if action == "start":
                await lifecycle.start_stack(cfg)
            elif action == "stop":
                await lifecycle.stop_stack()
            elif action == "queue_track":
                path = input.get("path", "")
                if not path:
                    return self._error("missing 'path'")
                await lifecycle.queue_track(path)
            elif action == "skip":
                await lifecycle.skip_current()
            elif action == "clear_queue":
                await lifecycle.clear_queue()
            elif action == "scan_library":
                lib = _get_library()
                target = input.get("dir") or cfg.get("music_dir")
                count = lib.scan(target)
                state = get_state()
                state.library_count = count
            else:
                return self._error(f"unknown action: {action}")
        except Exception as e:
            return self._error(str(e))
        return asdict(get_state())

    def _error(self, msg: str) -> dict:
        s = asdict(get_state())
        s["error"] = msg
        return s
```

- [ ] **Step 3: Write `api/library.py`**

```python
from dataclasses import asdict
from helpers.api import ApiHandler, Request

from usr.plugins.dj_booth.api.dj_control import _get_library


class Library(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        lib = _get_library()
        action = (input or {}).get("action", "list")
        if action == "list":
            page = int(input.get("page", 0))
            per_page = int(input.get("per_page", 50))
            query = input.get("query", "").strip()
            tracks = lib.search(query) if query else lib.tracks
            start = page * per_page
            end = start + per_page
            return {
                "total": len(tracks),
                "page": page,
                "per_page": per_page,
                "tracks": [asdict(t) for t in tracks[start:end]],
            }
        if action == "search":
            return {"tracks": [asdict(t) for t in lib.search(input.get("query", ""))]}
        if action == "get_track":
            t = lib.get_track(input.get("path", ""))
            return {"track": asdict(t) if t else None}
        return {"error": f"unknown action: {action}"}
```

- [ ] **Step 4: Smoke-test handler imports**

```bash
cd /Users/lazy/Desktop/agent-zero
python -c "from usr.plugins.dj_booth.api.dj_control import DjControl; from usr.plugins.dj_booth.api.stream_status import StreamStatus; from usr.plugins.dj_booth.api.library import Library; print('ok')"
```
Expected: `ok` printed, no ImportError.

- [ ] **Step 5: Commit**

```bash
git add usr/plugins/dj_booth/api/
git commit -m "feat(dj_booth): add api handlers for control, status, library"
```

---

### Task 9: hooks.py + execute.py

**Files:**
- Create: `usr/plugins/dj_booth/hooks.py`
- Create: `usr/plugins/dj_booth/execute.py`

- [ ] **Step 1: Write `hooks.py`**

```python
"""Plugin install/uninstall hooks for dj_booth."""
import os
import subprocess
import sys


def install():
    print("[dj_booth] installing system packages (icecast2, liquidsoap, ffmpeg)...")
    apt_packages = ["icecast2", "liquidsoap", "ffmpeg"]
    result = subprocess.run(
        ["apt-get", "install", "-y", "--no-install-recommends"] + apt_packages,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[dj_booth] WARNING: apt install failed (continuing): {result.stderr}")
    else:
        print("[dj_booth] system packages installed.")

    print("[dj_booth] installing python packages...")
    py_packages = ["mutagen>=1.47", "requests>=2.31"]
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet"] + py_packages,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[dj_booth] WARNING: pip install failed: {result.stderr}")
    else:
        print("[dj_booth] python packages installed.")

    music_dir = "/a0/usr/workdir/music"
    os.makedirs(music_dir, exist_ok=True)
    print(f"[dj_booth] music directory ready: {music_dir}")
    print("[dj_booth] install complete.")


def uninstall():
    print("[dj_booth] uninstalling — stopping services...")
    try:
        import asyncio
        from usr.plugins.dj_booth.helpers.lifecycle import stop_stack
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Best effort — schedule and don't block
                loop.create_task(stop_stack())
            else:
                loop.run_until_complete(stop_stack())
        except RuntimeError:
            asyncio.run(stop_stack())
    except Exception as e:
        print(f"[dj_booth] uninstall warning: {e}")
    print("[dj_booth] uninstall complete.")
```

- [ ] **Step 2: Write `execute.py`**

```python
"""User-triggered start. Runs on click in the Plugins UI."""
import asyncio
import sys


def main():
    print("[dj_booth] starting DJ Booth services...")
    try:
        from helpers.plugins import get_plugin_config
        from usr.plugins.dj_booth.helpers.lifecycle import start_stack
        from usr.plugins.dj_booth.helpers.library import LibraryManager
        from usr.plugins.dj_booth.api.dj_control import _get_library
        from usr.plugins.dj_booth.helpers.state import get_state

        cfg = get_plugin_config("dj_booth") or {}

        lib = _get_library()
        scanned = lib.scan(cfg.get("music_dir", "/a0/usr/workdir/music"))
        get_state().library_count = scanned
        print(f"[dj_booth] library scanned: {scanned} tracks")

        asyncio.run(start_stack(cfg))

        port = cfg.get("icecast_port", 8000)
        mount = cfg.get("mount", "/stream")
        print(f"[dj_booth] stream live at http://localhost:{port}{mount}")
        print("[dj_booth] tune in with VLC, Winamp, or any ICY-compatible client.")
        return 0
    except Exception as e:
        print(f"[dj_booth] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Verify import resolution (no spawn yet)**

```bash
cd /Users/lazy/Desktop/agent-zero
python -c "from usr.plugins.dj_booth import hooks, execute; print('imports ok')"
```

- [ ] **Step 4: Commit**

```bash
git add usr/plugins/dj_booth/hooks.py usr/plugins/dj_booth/execute.py
git commit -m "feat(dj_booth): add install hooks and execute entrypoint"
```

---

## Chunk 4: WebUI — store + modal + sidebar + config

### Task 10: Alpine store

**File:** Create `usr/plugins/dj_booth/webui/dj-store.js`

- [ ] **Step 1: Write the store**

```javascript
import { createStore } from "/js/AlpineStore.js";
import {
    toastFrontendError,
    toastFrontendSuccess,
    toastFrontendInfo,
} from "/components/notifications/notification-store.js";

const API_CONTROL = "/api/plugins/dj_booth/dj_control";
const API_STATUS  = "/api/plugins/dj_booth/stream_status";
const API_LIB     = "/api/plugins/dj_booth/library";

export const store = createStore("djBoothStore", {
    status: null,
    library: { tracks: [], total: 0, page: 0 },
    librarySearch: "",
    isOpen: false,
    pollInterval: null,
    searchDebounce: null,

    async init() {
        await this.fetchStatus();
    },

    async onOpen() {
        this.isOpen = true;
        await this.fetchStatus();
        await this.fetchLibrary();
        this.pollInterval = setInterval(() => this.fetchStatus(), 1000);
    },

    cleanup() {
        this.isOpen = false;
        if (this.pollInterval) clearInterval(this.pollInterval);
        this.pollInterval = null;
    },

    async fetchStatus() {
        try {
            const res = await fetch(API_STATUS);
            if (res.ok) this.status = await res.json();
        } catch (e) {
            // silent — toast on mutating calls only
        }
    },

    async _post(url, body) {
        try {
            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data && data.error) {
                toastFrontendError(data.error, "DJ Booth");
            }
            return data;
        } catch (e) {
            toastFrontendError(String(e), "DJ Booth");
            return null;
        }
    },

    async _control(action, params = {}) {
        const data = await this._post(API_CONTROL, { action, ...params });
        if (data && !data.error) this.status = data;
        return data;
    },

    async start() {
        const r = await this._control("start");
        if (r && !r.error) toastFrontendSuccess("Stream started", "DJ Booth");
    },
    async stop() {
        const r = await this._control("stop");
        if (r && !r.error) toastFrontendInfo("Stream stopped", "DJ Booth");
    },
    async skip() { await this._control("skip"); },
    async clearQueue() { await this._control("clear_queue"); },
    async queueTrack(path) {
        const r = await this._control("queue_track", { path });
        if (r && !r.error) toastFrontendInfo("Queued", "DJ Booth");
    },
    async scanLibrary() {
        const r = await this._control("scan_library");
        if (r && !r.error) {
            toastFrontendSuccess(`Scanned ${r.library_count} tracks`, "DJ Booth");
            await this.fetchLibrary();
        }
    },

    async fetchLibrary() {
        const data = await this._post(API_LIB, {
            action: "list",
            page: this.library.page,
            per_page: 100,
            query: this.librarySearch,
        });
        if (data && !data.error) this.library = data;
    },

    onSearchChange(val) {
        this.librarySearch = val;
        if (this.searchDebounce) clearTimeout(this.searchDebounce);
        this.searchDebounce = setTimeout(() => {
            this.library.page = 0;
            this.fetchLibrary();
        }, 300);
    },

    async copyStreamUrl() {
        if (!this.status?.stream_url) return;
        try {
            await navigator.clipboard.writeText(this.status.stream_url);
            toastFrontendSuccess("Stream URL copied", "DJ Booth");
        } catch (e) {
            toastFrontendError("Copy failed", "DJ Booth");
        }
    },

    get isRunning() { return this.status?.is_running || false; },
    get engineLabel() {
        if (!this.status?.engine) return "—";
        return this.status.engine === "ffmpeg" ? "FFMPEG (fallback)" : this.status.engine.toUpperCase();
    },
    get listenerCount() { return this.status?.listener_count || 0; },
    get currentTrack() { return this.status?.current_track || ""; },
    get queueList() { return this.status?.queue || []; },
});
```

- [ ] **Step 2: Commit**

```bash
git add usr/plugins/dj_booth/webui/dj-store.js
git commit -m "feat(dj_booth): add Alpine store with polling and toast errors"
```

---

### Task 11: Sidebar button

**File:** Create `usr/plugins/dj_booth/extensions/webui/sidebar-quick-actions-main-start/dj-button.html`

- [ ] **Step 1: Write the button**

```html
<div x-data x-move-after=".config-button#dashboard">
  <template x-if="$store.djBoothStore">
    <button
      class="config-button"
      @click="openModal('/plugins/dj_booth/webui/dj-booth.html')"
      title="DJ Booth"
    >
      <span class="icon">🎧</span>
      <span>DJ Booth</span>
    </button>
  </template>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add usr/plugins/dj_booth/extensions/
git commit -m "feat(dj_booth): add sidebar quick-action button"
```

---

### Task 12: Main modal `dj-booth.html`

**File:** Create `usr/plugins/dj_booth/webui/dj-booth.html`

- [ ] **Step 1: Write the modal**

```html
<head>
  <script type="module" src="/plugins/dj_booth/webui/dj-store.js"></script>
  <style>
    .djb-wrap { padding: 1rem; max-width: 1100px; margin: 0 auto; color: #e8e8f0; }
    .djb-header { display: flex; gap: 1rem; align-items: center; padding: 0.75rem 1rem;
                  background: #1a1a2e; border-radius: 8px; margin-bottom: 1rem; }
    .djb-header h2 { margin: 0 1rem 0 0; font-size: 1.1rem; }
    .djb-badge { padding: 0.15rem 0.5rem; background: #16213e; border-radius: 4px;
                 font: 0.75rem 'JetBrains Mono', monospace; color: #00d4ff; }
    .djb-badge.fallback { color: #ffbe0b; }
    .djb-listeners { display: flex; align-items: center; gap: 0.4rem; font: 0.85rem monospace; }
    .djb-pulse { width: 8px; height: 8px; border-radius: 50%; background: #00ff88;
                 box-shadow: 0 0 8px #00ff88; animation: pulse 2s infinite; }
    @keyframes pulse { 50% { opacity: 0.3; } }
    .djb-stream-url { flex: 1; font: 0.8rem monospace; color: #aaa; }
    .djb-btn { padding: 0.4rem 0.9rem; border-radius: 4px; border: 1px solid #3a3a4e;
               background: #16213e; color: #e8e8f0; cursor: pointer; }
    .djb-btn:hover { background: #233355; border-color: #00d4ff; }
    .djb-btn.start { background: #00ff88; color: #001a0c; border-color: #00ff88; }
    .djb-btn.stop  { background: #ff006e; color: #fff; border-color: #ff006e; }
    .djb-grid { display: grid; grid-template-columns: 2fr 3fr; gap: 1rem; }
    .djb-panel { background: #1a1a2e; padding: 1rem; border-radius: 8px; }
    .djb-panel h3 { margin-top: 0; font-size: 0.9rem; color: #00d4ff; text-transform: uppercase;
                    letter-spacing: 1px; }
    .djb-now { font: 1.2rem 'JetBrains Mono', monospace; padding: 0.5rem 0; }
    .djb-list { max-height: 280px; overflow-y: auto; font: 0.85rem monospace; }
    .djb-row { display: grid; grid-template-columns: 1fr 1fr 80px;
               padding: 0.3rem 0.4rem; gap: 0.5rem; cursor: pointer; border-radius: 3px; }
    .djb-row:hover { background: rgba(0, 212, 255, 0.1); }
    .djb-search { width: 100%; padding: 0.4rem; background: #0a0a0f;
                  border: 1px solid #3a3a4e; color: #e8e8f0; border-radius: 4px;
                  margin-bottom: 0.5rem; }
    .djb-empty { color: #888; font-style: italic; padding: 1rem; text-align: center; }
  </style>
</head>

<div x-data>
  <template x-if="$store.djBoothStore">
    <div x-init="$store.djBoothStore.onOpen()" x-destroy="$store.djBoothStore.cleanup()" class="djb-wrap">

      <div class="djb-header">
        <h2 x-text="$store.djBoothStore.status?.is_running ? '🎧 ON AIR' : '🎧 DJ Booth'"></h2>
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
        <button class="djb-btn"
                x-show="$store.djBoothStore.isRunning"
                @click="$store.djBoothStore.copyStreamUrl()">Copy URL</button>
        <button class="djb-btn start"
                x-show="!$store.djBoothStore.isRunning"
                @click="$store.djBoothStore.start()">Start</button>
        <button class="djb-btn stop"
                x-show="$store.djBoothStore.isRunning"
                @click="$store.djBoothStore.stop()">Stop</button>
      </div>

      <div class="djb-grid">
        <div class="djb-panel">
          <h3>Now Playing</h3>
          <div class="djb-now" x-text="$store.djBoothStore.currentTrack || '— silence —'"></div>

          <h3 style="margin-top:1rem;">Queue (<span x-text="$store.djBoothStore.queueList.length"></span>)</h3>
          <div class="djb-list">
            <template x-for="(p, i) in $store.djBoothStore.queueList" :key="i">
              <div class="djb-row"><span x-text="p" style="grid-column: span 3;"></span></div>
            </template>
            <div class="djb-empty" x-show="!$store.djBoothStore.queueList.length">queue empty</div>
          </div>
          <div style="margin-top:0.5rem; display:flex; gap:0.5rem;">
            <button class="djb-btn"
                    @click="$store.djBoothStore.skip()"
                    :disabled="!$store.djBoothStore.isRunning">Skip</button>
            <button class="djb-btn"
                    @click="$store.djBoothStore.clearQueue()"
                    :disabled="!$store.djBoothStore.isRunning">Clear</button>
          </div>
        </div>

        <div class="djb-panel">
          <h3>Library
            <button class="djb-btn" style="float:right; padding: 0.2rem 0.6rem; font-size: 0.8rem;"
                    @click="$store.djBoothStore.scanLibrary()">Scan</button>
          </h3>
          <input class="djb-search" type="text" placeholder="search title / artist / album"
                 :value="$store.djBoothStore.librarySearch"
                 @input.debounce.300ms="$store.djBoothStore.onSearchChange($event.target.value)">
          <div class="djb-list">
            <template x-for="t in $store.djBoothStore.library.tracks" :key="t.path">
              <div class="djb-row" @dblclick="$store.djBoothStore.queueTrack(t.path)" :title="t.path">
                <span x-text="t.title"></span>
                <span x-text="t.artist" style="color:#aaa;"></span>
                <span x-text="t.format" style="color:#666;"></span>
              </div>
            </template>
            <div class="djb-empty" x-show="!$store.djBoothStore.library.tracks.length">
              no tracks — click Scan
            </div>
          </div>
        </div>
      </div>
    </div>
  </template>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add usr/plugins/dj_booth/webui/dj-booth.html
git commit -m "feat(dj_booth): add minimal control modal"
```

---

### Task 13: Settings page `config.html`

**File:** Create `usr/plugins/dj_booth/webui/config.html`

Use whatever bind format the existing `_office` or `marimo_notebooks` plugins use for settings. If unsure, follow `usr/plugins/<any>/webui/config.html` from another plugin verbatim and substitute fields.

- [ ] **Step 1: Inspect existing config.html for binding pattern**

```bash
find /Users/lazy/Desktop/agent-zero -name "config.html" -path "*/usr/plugins/*" | head -3
```

Pick one and Read it. Mirror the `<input x-model="config.field_name">` pattern.

- [ ] **Step 2: Write `config.html` (template — adapt bindings to match found pattern)**

```html
<div x-data>
  <template x-if="$store.djBoothStore">
    <div>
      <h3>Stream</h3>
      <label>Stream Name <input type="text" x-model="config.stream_name"></label>
      <label>Description <input type="text" x-model="config.stream_description"></label>
      <label>Genre <input type="text" x-model="config.stream_genre"></label>
      <label>Public Listing <input type="checkbox" x-model="config.public_listing"></label>

      <h3>Server</h3>
      <label>Music Directory <input type="text" x-model="config.music_dir"></label>
      <label>Icecast Port <input type="number" x-model.number="config.icecast_port"></label>
      <label>Source Password <input type="password" x-model="config.icecast_source_password"></label>
      <label>Admin Password <input type="password" x-model="config.icecast_admin_password"></label>
      <label>Max Listeners <input type="number" x-model.number="config.max_listeners"></label>

      <h3>Audio</h3>
      <label>Bitrate
        <select x-model.number="config.bitrate">
          <option :value="64">64 kbps</option>
          <option :value="128">128 kbps</option>
          <option :value="192">192 kbps</option>
          <option :value="320">320 kbps</option>
        </select>
      </label>
    </div>
  </template>
</div>
```

- [ ] **Step 3: Commit**

```bash
git add usr/plugins/dj_booth/webui/config.html
git commit -m "feat(dj_booth): add plugin settings UI"
```

---

## Chunk 5: README + manual smoke test + Slice 1 close-out

### Task 14: README + manual smoke test pass

**File:** Create `usr/plugins/dj_booth/README.md`

- [ ] **Step 1: Write README**

```markdown
# dj_booth — Slice 1 (Stream Backbone)

Local Icecast2 streaming server packaged as an Agent Zero plugin. Any ICY-compatible client (Winamp, VLC, foobar2000, browser `<audio>`) can tune in.

## Status

Slice 1 of 5. Ships: Icecast2 + streaming engine (liquidsoap preferred, ffmpeg fallback) + library scan + minimal start/stop UI.

Coming in later slices: agent DJ tool (Slice 2), full DJ booth UI with two decks + EFX (Slice 3), BPM/key/spectrum analysis (Slice 4), mic + cue/loop/scratch (Slice 5).

## Prerequisites

- Agent Zero in Docker with `apt-get` available
- Port 8000 mapped on the container: `docker run -p 8000:8000 ...`
- Music files copied into the configured `music_dir` (default `/a0/usr/workdir/music`)

## Install

1. Open the Plugins UI in Agent Zero
2. Install `dj_booth`. The install hook runs `apt-get install icecast2 liquidsoap ffmpeg` and `pip install mutagen`.
3. Open Settings → DJ Booth and adjust passwords + paths
4. Click **Execute** in the plugin row to start the stack

If liquidsoap is unavailable on the host, the engine falls back to ffmpeg automatically (badge will read `FFMPEG (fallback)`). Streaming still works; brief silence between tracks is expected.

## Use

- Open the **🎧 DJ Booth** sidebar button → minimal control panel modal
- Click **Scan** in the Library panel after copying files into `music_dir`
- Double-click a track to queue it
- **Skip** / **Clear** buttons control the queue
- Listeners connect to `http://<host>:8000/stream` from VLC, Winamp, or browser

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Port 8000 in use" toast | Another icecast or unrelated service on 8000 | Change `icecast_port` in settings, restart |
| `FFMPEG (fallback)` badge | liquidsoap binary not in `$PATH` | `apt-get install liquidsoap`; restart |
| No audio in VLC | Stream is silent because queue is empty | Queue a track from the Library panel |
| Library shows 0 tracks after scan | `music_dir` empty or wrong path | Verify path in Settings, copy files in, click Scan again |
| Plugin restart leaves orphan processes | Manual SIGKILL'd process | Stale-PID sweep at next start cleans up; verify with `pgrep icecast2 liquidsoap ffmpeg` |

## Architecture

See `docs/superpowers/specs/2026-05-03-dj-booth-slice-1-design.md`.

## License

MIT.
```

- [ ] **Step 2: Manual smoke test (per spec §13)**

Execute these tests in a Docker A0 container with port 8000 mapped. Mark each as it passes:

- [ ] Plugin appears in Plugins UI
- [ ] Install hook completes without error
- [ ] Click Execute → terminal shows "stream live at http://localhost:8000/stream"
- [ ] `pgrep icecast2` returns a PID, `pgrep liquidsoap` (or `ffmpeg`) returns a PID
- [ ] VLC connects to `http://localhost:8000/stream` and plays silence
- [ ] Drop 3 mp3 files into `music_dir`, click Scan → 3 tracks listed
- [ ] Double-click a track → queue size becomes 1, "Now Playing" updates within 5s
- [ ] Skip mid-track → next queued plays
- [ ] Disconnect VLC → listener count returns to 0 within 10s
- [ ] Click Stop → `pgrep icecast2 liquidsoap ffmpeg` returns nothing
- [ ] No leftover `/tmp/dj_booth_*.pid` files
- [ ] Restart (Stop → Start) → boots cleanly
- [ ] Test ffmpeg fallback: `mv $(which liquidsoap) /tmp/liq.bak`, restart, badge shows `FFMPEG (fallback)`, audio still streams. Restore: `mv /tmp/liq.bak $(which liquidsoap || echo /usr/bin/liquidsoap)`.

- [ ] **Step 3: If any smoke test fails, file the failure mode in this README's troubleshooting table and fix in code before closing the slice.**

- [ ] **Step 4: Commit**

```bash
git add usr/plugins/dj_booth/README.md
git commit -m "docs(dj_booth): add Slice 1 README and troubleshooting"
```

---

### Task 15: Slice 1 close-out

- [ ] **Step 1: Run full plugin test suite**

```bash
cd /Users/lazy/Desktop/agent-zero
python -m pytest usr/plugins/dj_booth/tests/ -v
```
Expected: all green.

- [ ] **Step 2: Verify acceptance criteria from spec §14**

Open `docs/superpowers/specs/2026-05-03-dj-booth-slice-1-design.md` §14 and tick each box. Anything unchecked = blocker for slice close.

- [ ] **Step 3: Tag the slice**

```bash
git tag -a dj_booth/slice-1-complete -m "dj_booth Slice 1: stream backbone shipped"
```

- [ ] **Step 4: Open Slice 2 brainstorming**

Slice 2 scope: agent `dj_tool` + agent profile + system_prompt extension. Create a fresh brainstorming session referencing this completed slice.

---

## Notes for the implementer

- **Don't add features from the parent spec that aren't explicitly listed in this plan.** Spec §15 lists what's deferred. Crossfade, EFX, BPM, decks, spectrum, mic, agent tool — all later slices.
- **If a test fails in a way the plan didn't anticipate**, stop, surface the failure, don't paper over it.
- **If the A0 plugin loader rejects the plugin at discovery**, check `helpers/plugins.py` around line 798 (`usr/plugins/<plugin_name>/`) to confirm directory naming matches.
- **Liquidsoap in particular is finicky** — the script must compile (`liquidsoap --check /tmp/dj_booth.liq` is a useful local sanity check). If startup fails, dump stderr to a log file in `/tmp/dj_booth_logs/` for diagnostics.
- **Tests use `pytest-asyncio`** — confirm `pytest-asyncio` is installed before running engine/lifecycle tests.
- **Frequent commits.** Each task ends with a commit. Don't bundle multiple tasks into one commit.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-03-dj-booth-slice-1.md`.**
