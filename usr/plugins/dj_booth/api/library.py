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
        if action == "analyze":
            path = input.get("path", "")
            if not path:
                return {"error": "missing 'path'"}
            t = await lib.analyze(path)
            return {"track": asdict(t) if t else None}
        return {"error": f"unknown action: {action}"}
