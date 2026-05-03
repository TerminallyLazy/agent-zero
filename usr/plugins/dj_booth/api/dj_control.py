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
