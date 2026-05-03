"""Agent-callable DJ control tool. Slice 3 scope — deck-aware methods + mixer."""
from __future__ import annotations

from helpers.tool import Tool, Response


class DjTool(Tool):
    """
    Agent-callable DJ control. Sub-methods dispatched via `self.method`:

      dj_tool:status              — current stream state summary
      dj_tool:search_library      — args.query → matching tracks
      dj_tool:queue_track         — args.path (+ args.deck="a"|"b") → add track to deck queue
      dj_tool:skip                — args.deck="a"|"b" → skip current track on deck
      dj_tool:clear_queue         — args.deck="a"|"b" → clear queued tracks on deck
      dj_tool:listener_count      — current listener count
      dj_tool:set_crossfader      — args.position 0.0..1.0 (0=A, 1=B)
      dj_tool:set_volume          — args.channel ("deck_a"|"deck_b"|"master") + args.level
      dj_tool:set_eq              — args.deck + args.low/mid/high (-12..+12 dB)

    Deferred to later slices: load_track, set_efx, announce, cue/loop/scratch.
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
                deck = self.args.get("deck", "a")
                if not path:
                    return Response(message="dj_tool: queue_track requires 'path'", break_loop=False)
                await lifecycle.queue_track(path, deck)
                msg = f"queued {path} on deck {deck.upper()}"
            elif method == "skip":
                from usr.plugins.dj_booth.helpers import lifecycle
                deck = self.args.get("deck", "a")
                await lifecycle.skip_current(deck)
                msg = f"skipped current track on deck {deck.upper()}"
            elif method == "clear_queue":
                from usr.plugins.dj_booth.helpers import lifecycle
                deck = self.args.get("deck", "a")
                await lifecycle.clear_queue(deck)
                msg = f"queue cleared on deck {deck.upper()}"
            elif method == "listener_count":
                from usr.plugins.dj_booth.helpers.state import get_state
                msg = f"listeners: {get_state().listener_count}"
            elif method == "set_crossfader":
                from usr.plugins.dj_booth.helpers import lifecycle
                position = float(self.args.get("position", 0.5))
                await lifecycle.set_crossfader(position)
                msg = f"crossfader set to {position:.2f}"
            elif method == "set_volume":
                from usr.plugins.dj_booth.helpers import lifecycle
                channel = self.args.get("channel", "deck_a")
                level = float(self.args.get("level", 1.0))
                await lifecycle.set_volume(channel, level)
                msg = f"volume set: {channel} = {level:.2f}"
            elif method == "set_eq":
                from usr.plugins.dj_booth.helpers import lifecycle
                deck = self.args.get("deck", "a")
                low = float(self.args.get("low", 0.0))
                mid = float(self.args.get("mid", 0.0))
                high = float(self.args.get("high", 0.0))
                await lifecycle.set_eq(deck, low, mid, high)
                msg = f"EQ set on deck {deck.upper()}: low={low:+.1f} mid={mid:+.1f} high={high:+.1f}"
            else:
                msg = (
                    f"dj_tool: unknown method '{method}'. "
                    f"Valid: status, search_library, queue_track, skip, clear_queue, "
                    f"listener_count, set_crossfader, set_volume, set_eq."
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
            f"Deck A: {s.deck_a.current_track or '(silence)'} | queue={len(s.deck_a.queue)}\n"
            f"Deck B: {s.deck_b.current_track or '(silence)'} | queue={len(s.deck_b.queue)}\n"
            f"Mixer: crossfader={s.mixer.crossfader:.2f} master={s.mixer.master_volume:.2f}\n"
            f"Listeners: {s.listener_count}"
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
