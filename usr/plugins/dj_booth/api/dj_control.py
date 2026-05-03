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
            elif action == "scan_library":
                lib = _get_library()
                target = input.get("dir") or cfg.get("music_dir")
                count = lib.scan(target)
                state = get_state()
                state.library_count = count
            elif action == "set_pitch":
                await lifecycle.set_pitch(input.get("deck", "a"), float(input.get("semitones", 0.0)))
            elif action == "set_efx":
                await lifecycle.set_efx(
                    input.get("effect", ""),
                    input.get("param", ""),
                    input.get("value", 0.0),
                )
            elif action == "announce":
                await lifecycle.announce(input.get("text", ""))
            elif action == "start_share":
                # Non-blocking: kicks off tunnel in background. Frontend polls
                # /stream_status to pick up public_url when ready.
                await lifecycle.start_public_share()
            elif action == "stop_share":
                await lifecycle.stop_public_share()
            elif action == "sync_bpm":
                src_bpm = float(input.get("source_bpm", 0.0))
                tgt_bpm = float(input.get("target_bpm", 0.0))
                deck = input.get("target_deck", "b")
                if src_bpm <= 0 or tgt_bpm <= 0:
                    return self._error("sync_bpm requires source_bpm and target_bpm > 0")
                import math
                semitones = max(-6.0, min(6.0, 12.0 * math.log2(src_bpm / tgt_bpm)))
                await lifecycle.set_pitch(deck, semitones)
            else:
                return self._error(f"unknown action: {action}")
        except Exception as e:
            return self._error(str(e))
        return asdict(get_state())

    def _error(self, msg: str) -> dict:
        s = asdict(get_state())
        s["error"] = msg
        return s
