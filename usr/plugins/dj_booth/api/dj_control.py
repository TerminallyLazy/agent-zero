from dataclasses import asdict
from helpers.api import ApiHandler, Request

from usr.plugins.dj_booth.helpers import lifecycle
from usr.plugins.dj_booth.helpers.library import LibraryManager
from usr.plugins.dj_booth.helpers.state import get_state
from usr.plugins.dj_booth.helpers.runtime import run_async
from helpers.plugins import get_plugin_config


_library: LibraryManager | None = None


def _get_library() -> LibraryManager:
    global _library
    if _library is None:
        _library = LibraryManager()
    return _library


class DjControl(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        # Every async lifecycle call is forwarded to the persistent runtime
        # (helpers/runtime.py) so the long-running tasks they spawn — IcyServer,
        # ffmpeg engine loop, health loop, spectrum loop, tunnel runner —
        # don't get cancelled when this Flask request returns.
        action = (input or {}).get("action", "")
        cfg = get_plugin_config("dj_booth") or {}
        try:
            if action == "start":
                await run_async(lifecycle.start_stack(cfg), timeout=60.0)
            elif action == "stop":
                await run_async(lifecycle.stop_stack(), timeout=30.0)
            elif action == "queue_track":
                path = input.get("path", "")
                deck = input.get("deck", "a")
                if not path:
                    return self._error("missing 'path'")
                await run_async(lifecycle.queue_track(path, deck), timeout=10.0)
            elif action == "skip":
                await run_async(lifecycle.skip_current(input.get("deck", "a")), timeout=10.0)
            elif action == "clear_queue":
                await run_async(lifecycle.clear_queue(input.get("deck", "a")), timeout=10.0)
            elif action == "set_crossfader":
                await run_async(lifecycle.set_crossfader(float(input.get("position", 0.5))), timeout=5.0)
            elif action == "set_volume":
                await run_async(
                    lifecycle.set_volume(input.get("channel", "deck_a"), float(input.get("level", 1.0))),
                    timeout=5.0,
                )
            elif action == "set_eq":
                await run_async(
                    lifecycle.set_eq(
                        input.get("deck", "a"),
                        float(input.get("low", 0.0)),
                        float(input.get("mid", 0.0)),
                        float(input.get("high", 0.0)),
                    ),
                    timeout=5.0,
                )
            elif action == "scan_library":
                # Library scan is sync + cheap — no need to schedule on the runtime.
                lib = _get_library()
                target = input.get("dir") or cfg.get("music_dir")
                count = lib.scan(target)
                get_state().library_count = count
            elif action == "set_pitch":
                await run_async(
                    lifecycle.set_pitch(input.get("deck", "a"), float(input.get("semitones", 0.0))),
                    timeout=5.0,
                )
            elif action == "set_efx":
                await run_async(
                    lifecycle.set_efx(
                        input.get("effect", ""),
                        input.get("param", ""),
                        input.get("value", 0.0),
                    ),
                    timeout=5.0,
                )
            elif action == "announce":
                await run_async(lifecycle.announce(input.get("text", "")), timeout=30.0)
            elif action == "start_share":
                # Non-blocking — schedules a background task on the runtime.
                # Frontend polls /stream_status and picks up public_url when ready.
                await run_async(lifecycle.start_public_share(), timeout=5.0)
            elif action == "stop_share":
                await run_async(lifecycle.stop_public_share(), timeout=10.0)
            elif action == "sync_bpm":
                src_bpm = float(input.get("source_bpm", 0.0))
                tgt_bpm = float(input.get("target_bpm", 0.0))
                deck = input.get("target_deck", "b")
                if src_bpm <= 0 or tgt_bpm <= 0:
                    return self._error("sync_bpm requires source_bpm and target_bpm > 0")
                import math
                semitones = max(-6.0, min(6.0, 12.0 * math.log2(src_bpm / tgt_bpm)))
                await run_async(lifecycle.set_pitch(deck, semitones), timeout=5.0)
            else:
                return self._error(f"unknown action: {action}")
        except Exception as e:
            return self._error(str(e))
        return asdict(get_state())

    def _error(self, msg: str) -> dict:
        s = asdict(get_state())
        s["error"] = msg
        return s
