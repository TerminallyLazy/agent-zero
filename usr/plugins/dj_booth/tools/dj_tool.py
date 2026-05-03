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
      dj_tool:set_pitch           — args.deck + args.semitones (-6..+6 st)
      dj_tool:set_efx             — args.effect + args.param + args.value
      dj_tool:announce            — args.text → TTS + inject into stream
      dj_tool:sync_bpm            — args.source_path + args.target_path (+ args.target_deck="b") → match BPM via pitch

    Deferred to later slices: load_track, cue/loop/scratch.
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
            elif method == "set_pitch":
                from usr.plugins.dj_booth.helpers import lifecycle
                deck = self.args.get("deck", "a")
                semitones = float(self.args.get("semitones", 0.0))
                await lifecycle.set_pitch(deck, semitones)
                msg = f"pitch set on deck {deck.upper()}: {semitones:+.2f} st"
            elif method == "set_efx":
                from usr.plugins.dj_booth.helpers import lifecycle
                effect = self.args.get("effect", "")
                param = self.args.get("param", "")
                value = self.args.get("value", 0.0)
                if not effect or not param:
                    return Response(message="dj_tool: set_efx requires 'effect' and 'param'", break_loop=False)
                await lifecycle.set_efx(effect, param, value)
                msg = f"EFX {effect}.{param} = {value}"
            elif method == "announce":
                from usr.plugins.dj_booth.helpers import lifecycle
                text = self.args.get("text", "")
                if not text.strip():
                    return Response(message="dj_tool: announce requires non-empty 'text'", break_loop=False)
                await lifecycle.announce(text)
                msg = f"announced: {text}"
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
                    return Response(
                        message="sync_bpm: tracks must be analyzed first (BPM>0)",
                        break_loop=False,
                    )
                semitones = max(-6.0, min(6.0, 12.0 * math.log2(src.bpm / tgt.bpm)))
                await lifecycle.set_pitch(target_deck, semitones)
                msg = f"sync'd deck {target_deck.upper()} to {src.bpm} BPM (pitch {semitones:+.2f} st)"
            else:
                msg = (
                    f"dj_tool: unknown method '{method}'. "
                    f"Valid: status, search_library, queue_track, skip, clear_queue, "
                    f"listener_count, set_crossfader, set_volume, set_eq, analyze_track, "
                    f"set_pitch, set_efx, announce, sync_bpm."
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
