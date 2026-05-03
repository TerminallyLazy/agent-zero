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
