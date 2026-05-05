"""GET/POST /api/plugins/jcode_harness/list_sessions.

Lists resumable sessions by reading the ``~/.jcode/sessions/`` journal
directory. Spike 0.2 finding: ``jcode`` exposes no ``session list --json``
subcommand, so we read the on-disk session journals directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from helpers.api import ApiHandler, Request


class ListSessions(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict:
        base = Path.home() / ".jcode" / "sessions"
        if not base.exists():
            return {"sessions": []}
        sessions: list[dict] = []
        for sess_dir in base.iterdir():
            if not sess_dir.is_dir():
                continue
            snap = sess_dir / "session.json"
            if not snap.is_file():
                continue
            try:
                data = json.loads(snap.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            sessions.append(
                {
                    "id": sess_dir.name,
                    "title": data.get("title", ""),
                    "provider_key": data.get("provider_key", "jcode"),
                    "working_dir": data.get("working_dir", ""),
                    "updated_at": data.get("updated_at"),
                    "model": data.get("model"),
                    "provider_session_id": data.get("provider_session_id"),
                }
            )
        sessions.sort(key=lambda s: s.get("updated_at") or 0, reverse=True)
        return {"sessions": sessions}
