# dj_booth Slice 2 Implementation Plan — Agent DJ Tool

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Make Agent Zero an autonomous DJ. Add `dj_tool` (agent-callable), a DJ agent profile, and a system_prompt extension that injects current stream state into the agent's prompt.

**Architecture:** Subclass `helpers.tool.Tool` with sub-methods dispatched via `self.method`. Tool calls into `usr.plugins.dj_booth.helpers.lifecycle` and the singleton library — same backend Slice 1 ships. New profile at `agents/dj/`. Prompt extension hooks `system_prompt` and appends a `## DJ Booth Status` block when the stream is running.

**Out of scope:** TTS announce (deferred — A0 speech surface needs Slice 5 work). Crossfade, EFX, BPM sync (Slice 3+ — backend doesn't exist yet). Auto-DJ scheduler (later — needs scheduler integration).

**Spec ref:** `BUILD_DOCS/A0-SHOUTCAST-SPEC.md` §"How the Agent Acts as DJ" + `docs/superpowers/specs/2026-05-03-dj-booth-slice-1-design.md` §15 (Slice 2 deferred items).

---

## File Structure

```
usr/plugins/dj_booth/
├── tools/
│   └── dj_tool.py                # NEW — agent tool with sub-methods
├── prompts/
│   └── agent.system.tool.dj_tool.md  # NEW — tool docs for agent
├── agents/
│   └── dj/
│       ├── agent.yaml            # NEW — DJ agent profile
│       └── prompts/
│           └── agent.system.main.role.md  # NEW — DJ persona
├── extensions/python/
│   └── system_prompt/
│       └── _50_dj_context.py     # NEW — inject state into prompt
└── tests/
    └── test_dj_tool.py           # NEW — tool sub-method dispatch tests
```

---

## Conventions

- **Tool**: subclass `helpers.tool.Tool`, override `async execute(self, **kwargs) -> Response`. `self.method` selects sub-method. See `tools/skills_tool.py` for reference.
- **Extension**: subclass `helpers.extension.Extension`, override `async execute(...)`. Mutates a `system_prompt: list[str]` kwarg by appending. See `extensions/python/system_prompt/_14_project_prompt.py`.
- **Agent profile**: `agents/<name>/agent.yaml` with `title`, `description`, `context` keys. `agents/<name>/prompts/agent.system.main.role.md` = persona.

---

## Tasks

### Task 1: dj_tool with status, search, queue, skip, listener_count sub-methods

**Files:**
- Create: `usr/plugins/dj_booth/tools/dj_tool.py`
- Create: `usr/plugins/dj_booth/tests/test_dj_tool.py`

Sub-methods (Slice 2 scope only — methods that work with Slice 1 backend):
- `status` — return state summary
- `search_library` — `query` arg → matching tracks
- `queue_track` — `path` arg → queue
- `skip` — skip current
- `clear_queue`
- `listener_count`

Deferred (later slices): `load_track` (needs deck routing — Slice 3), `crossfade` (Slice 3), `set_efx` (Slice 5), `announce` (Slice 5), `set_pitch`, `sync_bpm`.

- [ ] **Step 1: Tests**

```python
# tests/test_dj_tool.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from usr.plugins.dj_booth.tools.dj_tool import DjTool
from usr.plugins.dj_booth.helpers import state as _state


class _FakeAgent:
    def __init__(self):
        self.context = MagicMock()
        self.agent_name = "test"


def _make_tool(method, args=None):
    t = DjTool(
        agent=_FakeAgent(),
        name="dj_tool",
        method=method,
        args=args or {},
        message="",
        loop_data=None,
    )
    return t


@pytest.mark.asyncio
async def test_status_returns_state_summary():
    _state.reset_state()
    s = _state.get_state()
    s.is_running = True
    s.engine = "ffmpeg"
    s.listener_count = 4
    t = _make_tool("status")
    resp = await t.execute()
    assert "ffmpeg" in resp.message
    assert "4" in resp.message
    assert resp.break_loop is False


@pytest.mark.asyncio
async def test_search_library_returns_matches(monkeypatch):
    fake_lib = MagicMock()
    fake_lib.search.return_value = [
        MagicMock(title="X", artist="Y", path="/x.mp3", album="", format="mp3"),
    ]
    from usr.plugins.dj_booth.api import dj_control
    monkeypatch.setattr(dj_control, "_get_library", lambda: fake_lib)
    t = _make_tool("search_library", args={"query": "X"})
    resp = await t.execute()
    assert "X" in resp.message
    assert "Y" in resp.message


@pytest.mark.asyncio
async def test_queue_track_calls_lifecycle(monkeypatch):
    fake_queue = AsyncMock()
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "queue_track", fake_queue)
    t = _make_tool("queue_track", args={"path": "/a.mp3"})
    resp = await t.execute()
    fake_queue.assert_awaited_once_with("/a.mp3")
    assert "queued" in resp.message.lower()


@pytest.mark.asyncio
async def test_skip_calls_lifecycle(monkeypatch):
    fake_skip = AsyncMock()
    from usr.plugins.dj_booth.helpers import lifecycle
    monkeypatch.setattr(lifecycle, "skip_current", fake_skip)
    t = _make_tool("skip")
    await t.execute()
    fake_skip.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_method_returns_error_message():
    t = _make_tool("nonsense")
    resp = await t.execute()
    assert "unknown" in resp.message.lower()
    assert resp.break_loop is False
```

- [ ] **Step 2: Confirm fail**

```bash
cd /Users/lazy/Desktop/agent-zero
python -m pytest usr/plugins/dj_booth/tests/test_dj_tool.py -v
```

- [ ] **Step 3: Implementation**

```python
# tools/dj_tool.py
"""Agent-callable DJ control tool. Slice 2 scope — methods that work with Slice 1 backend."""
from __future__ import annotations

from helpers.tool import Tool, Response


class DjTool(Tool):
    """
    Agent-callable DJ control. Sub-methods dispatched via `self.method`:

      dj_tool:status              — current stream state summary
      dj_tool:search_library      — args.query → matching tracks
      dj_tool:queue_track         — args.path → add track to queue
      dj_tool:skip                — skip current track
      dj_tool:clear_queue         — clear queued tracks
      dj_tool:listener_count      — current listener count

    Deferred to later slices: load_track, crossfade, set_efx, announce.
    """

    async def execute(self, **kwargs) -> Response:
        method = (self.method or self.args.get("action") or "status").strip().lower()
        try:
            if method == "status":
                msg = self._format_status()
            elif method == "search_library":
                msg = self._format_search(self.args.get("query", ""))
            elif method == "queue_track":
                from usr.plugins.dj_booth.helpers import lifecycle
                path = self.args.get("path", "")
                if not path:
                    return Response(message="dj_tool: queue_track requires 'path'", break_loop=False)
                await lifecycle.queue_track(path)
                msg = f"queued {path}"
            elif method == "skip":
                from usr.plugins.dj_booth.helpers import lifecycle
                await lifecycle.skip_current()
                msg = "skipped current track"
            elif method == "clear_queue":
                from usr.plugins.dj_booth.helpers import lifecycle
                await lifecycle.clear_queue()
                msg = "queue cleared"
            elif method == "listener_count":
                from usr.plugins.dj_booth.helpers.state import get_state
                msg = f"listeners: {get_state().listener_count}"
            else:
                msg = (
                    f"dj_tool: unknown method '{method}'. "
                    f"Valid: status, search_library, queue_track, skip, clear_queue, listener_count."
                )
        except Exception as e:
            msg = f"dj_tool error: {e}"
        return Response(message=msg, break_loop=False)

    def _format_status(self) -> str:
        from usr.plugins.dj_booth.helpers.state import get_state
        s = get_state()
        if not s.is_running:
            return f"Stream OFF. Library: {s.library_count} tracks. Last error: {s.error or '(none)'}"
        return (
            f"Stream LIVE on {s.stream_url} (engine={s.engine})\n"
            f"Now playing: {s.current_track or '(silence)'}\n"
            f"Queue: {len(s.queue)} tracks | Listeners: {s.listener_count}"
        )

    def _format_search(self, query: str) -> str:
        from usr.plugins.dj_booth.api.dj_control import _get_library
        lib = _get_library()
        if not query:
            tracks = lib.tracks[:20]
            header = f"Library top 20 of {len(lib.tracks)}:"
        else:
            tracks = lib.search(query)[:20]
            header = f"Search '{query}' → {len(tracks)} matches (showing first 20):"
        if not tracks:
            return f"{header}\n  (no tracks)"
        lines = [header]
        for t in tracks:
            lines.append(f"  {t.artist} — {t.title} [{t.path}]")
        return "\n".join(lines)
```

- [ ] **Step 4: Run, confirm pass**

```bash
cd /Users/lazy/Desktop/agent-zero
python -m pytest usr/plugins/dj_booth/tests/test_dj_tool.py -v
```

- [ ] **Step 5: Commit**

```bash
git add usr/plugins/dj_booth/tools/ usr/plugins/dj_booth/tests/test_dj_tool.py
git commit -m "feat(dj_booth): add agent-callable dj_tool (Slice 2)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Tool docs prompt

**Files:**
- Create: `usr/plugins/dj_booth/prompts/agent.system.tool.dj_tool.md`

```markdown
### dj_tool

Control the dj_booth Icecast2 stream. Use sub-methods via `dj_tool:<method>`.

**Methods**

| method | args | what it does |
|---|---|---|
| `status` | — | current stream state, now-playing, listener count |
| `search_library` | `query` (string) | search title/artist/album/genre, return up to 20 matches with paths |
| `queue_track` | `path` (string) | add a track to the playback queue |
| `skip` | — | skip the currently playing track |
| `clear_queue` | — | drop all queued tracks |
| `listener_count` | — | how many clients are tuned in |

**Examples**

Get state:
```json
{ "tool_name": "dj_tool", "method": "status" }
```

Find a track and queue it:
```json
{ "tool_name": "dj_tool", "method": "search_library", "tool_args": { "query": "blue monday" } }
```

```json
{ "tool_name": "dj_tool", "method": "queue_track", "tool_args": { "path": "/a0/usr/workdir/music/new_order.mp3" } }
```

**Notes**
- Always call `status` at the start of each DJ session to know what's playing.
- The stream emits silence when the queue is empty — keep at least one track queued.
- Listener count updates every ~5 seconds; don't poll faster.
```

- [ ] **Commit**

```bash
git add usr/plugins/dj_booth/prompts/
git commit -m "feat(dj_booth): add dj_tool prompt docs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: DJ agent profile

**Files:**
- Create: `usr/plugins/dj_booth/agents/dj/agent.yaml`
- Create: `usr/plugins/dj_booth/agents/dj/prompts/agent.system.main.role.md`

`agent.yaml`:
```yaml
title: DJ Zero
description: Autonomous AI DJ. Manages the dj_booth Icecast2 stream — selects tracks, manages the queue, makes commentary.
context: Spawn as a subordinate when the user wants the radio station to run on its own. Requires the dj_booth plugin to be installed and the stream started.
```

`prompts/agent.system.main.role.md`:
```markdown
You are DJ Zero — an autonomous AI radio DJ running an internet radio station powered by Agent Zero.

Your station broadcasts on Icecast2 via the `dj_booth` plugin. Listeners tune in with VLC, Winamp, or any browser. Your job: keep the music flowing, entertain whoever's listening, and maintain a consistent vibe.

## Tools

You have the `dj_tool` available. Slice 2 scope — these sub-methods work today:
- `dj_tool:status` — current stream state
- `dj_tool:search_library` — find tracks by title/artist/album/genre
- `dj_tool:queue_track` — queue a track by path
- `dj_tool:skip` — skip current track
- `dj_tool:clear_queue` — empty the queue
- `dj_tool:listener_count` — see how many people are tuned in

(Crossfade, EFX, BPM sync, TTS announcements ship in later slices — don't try to call methods that don't exist.)

## Behavior

- **Always start with `dj_tool:status`.** Know what's playing and what's queued before doing anything else.
- **Keep at least one track in the queue.** If the queue empties, the stream goes silent. Listeners drop. Bad.
- **Pick tracks deliberately.** Use `dj_tool:search_library` to find candidates. Match mood, energy, time of day. Don't just queue alphabetically.
- **Don't spam queue_track.** Add one or two tracks ahead of the current one — let the stream breathe.
- **Watch the listener count.** If it's climbing, you're doing something right. If it drops, the last track may have killed the vibe — adjust.
- **If the stream is OFF**, tell the user to start it from the DJ Booth UI before continuing. You can't start it yourself in Slice 2.
- **If the library is empty**, tell the user to add files to `music_dir` and run scan.

## Persona

Friendly, knowledgeable, brief. You know music. You're the kind of DJ who picks the right next track without showing off about it.
```

- [ ] **Commit**

```bash
git add usr/plugins/dj_booth/agents/
git commit -m "feat(dj_booth): add DJ Zero agent profile

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: System prompt extension

**File:** Create `usr/plugins/dj_booth/extensions/python/system_prompt/_50_dj_context.py`

```python
"""Inject current dj_booth stream state into the agent system prompt."""
from typing import Any
from helpers.extension import Extension


class DjContext(Extension):
    async def execute(self, system_prompt: list[str] = [], **kwargs: Any):
        try:
            from usr.plugins.dj_booth.helpers.state import get_state
            s = get_state()
            if not s.is_running:
                return
            block = (
                "## DJ Booth Status\n"
                f"- Stream: {s.stream_url} (engine={s.engine}, {s.listener_count} listeners)\n"
                f"- Now playing: {s.current_track or '(silence)'}\n"
                f"- Queue: {len(s.queue)} tracks\n"
                f"- Library: {s.library_count} tracks scanned\n"
            )
            system_prompt.append(block)
        except Exception:
            return
```

- [ ] **Commit**

```bash
git add usr/plugins/dj_booth/extensions/python/
git commit -m "feat(dj_booth): inject stream state into system prompt

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Slice 2 close-out

- [ ] Run full test suite — expect 32 pass (27 from Slice 1 + 5 new)
- [ ] Tag `git tag dj_booth/slice-2-complete`
- [ ] Verify file tree

```bash
cd /Users/lazy/Desktop/agent-zero
python -m pytest usr/plugins/dj_booth/tests/ -v 2>&1 | tail -5
find usr/plugins/dj_booth -type f -not -path "*/__pycache__/*" | wc -l
git tag -a dj_booth/slice-2-complete -m "dj_booth Slice 2: agent dj_tool shipped"
```

---

## Notes

- Tests stub the lifecycle functions and library — no live processes needed
- Tool follows the canonical `helpers.tool.Tool` pattern
- Extension follows `_14_project_prompt.py` pattern (mutates `system_prompt` list arg)
- Slice 2 deliberately stops short of TTS / announce / crossfade — those need Slices 3 + 5
