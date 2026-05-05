"""jcode_resume: list cross-harness resumable sessions, or resume one by id.

Two modes based on whether ``session_id`` is supplied:

* **List mode** (``session_id is None``): read ``~/.jcode/sessions/`` directly
  (Spike 0.2: there is no ``jcode session list --json`` subcommand). Each
  session directory contains a ``session.json`` snapshot which we summarise
  and return grouped by ``provider_key``.
* **Resume mode** (``session_id`` provided): spin up the daemon, subscribe
  with ``allow_session_takeover=True`` and ``target_session_id=session_id``,
  request the history snapshot, and return a one-line summary.

Spec ref: §3 "Cross-harness session resume", §6.2.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from helpers.tool import Tool, Response

from usr.plugins.jcode_harness.helpers.daemon import (
    DaemonSupervisor,
    NoCredentialsError,
    locate_jcode_binary,
)
from usr.plugins.jcode_harness.helpers.jcode_client import JcodeClient
from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
from usr.plugins.jcode_harness.helpers.persistence import (
    get_or_create_client_instance_id,
)


_LIST_CAP = 20


def _list_sessions() -> list[dict]:
    """Read ``~/.jcode/sessions/`` journal directory (Spike 0.2).

    Each session directory is expected to contain a ``session.json`` snapshot
    with at least ``title``, ``provider_key``, ``working_dir``, and
    ``updated_at``. Missing fields default; corrupt files are skipped.
    """
    base = Path.home() / ".jcode" / "sessions"
    if not base.exists():
        return []
    out: list[dict] = []
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
        out.append(
            {
                "id": sess_dir.name,
                "title": data.get("title", ""),
                "provider_key": data.get("provider_key", "jcode"),
                "working_dir": data.get("working_dir", ""),
                "updated_at": data.get("updated_at"),
            }
        )
    out.sort(key=lambda s: s.get("updated_at") or 0, reverse=True)
    return out


class JcodeResume(Tool):
    """List jcode sessions across harnesses, or resume one by id."""

    async def execute(
        self,
        session_id: str | None = None,
        working_dir: str | None = None,
        **_kwargs,
    ) -> Response:
        if session_id is None:
            sessions = _list_sessions()
            if not sessions:
                return Response(
                    message="(no resumable sessions found)",
                    break_loop=False,
                )
            lines = [
                f"{s['id']} [{s['provider_key']}] {s['title'] or '(untitled)'}"
                for s in sessions[:_LIST_CAP]
            ]
            return Response(message="\n".join(lines), break_loop=False)

        # Resume mode
        wd = os.path.abspath(working_dir or os.getcwd())
        bin_path = locate_jcode_binary()
        if not bin_path:
            return Response(
                message="jcode binary not installed",
                break_loop=False,
            )

        sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
        try:
            sock = await sup.ensure_running(wd)
        except NoCredentialsError as e:
            return Response(message=str(e), break_loop=False)

        cid = get_or_create_client_instance_id(self.agent.context.id)
        client = JcodeClient()
        await client.connect(sock)
        try:
            await client.subscribe(
                wd, session_id, cid, allow_session_takeover=True
            )
            await client.get_history()
            history_ev = await client._recv_until(
                lambda e: e.type == "history"
            )
            messages_count = len(getattr(history_ev, "messages", []) or [])
            return Response(
                message=(
                    f"Resumed session {session_id}: "
                    f"{messages_count} prior messages"
                ),
                break_loop=False,
            )
        finally:
            await client.close()
