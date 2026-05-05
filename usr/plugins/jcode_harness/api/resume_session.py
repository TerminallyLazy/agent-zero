"""POST /api/plugins/jcode_harness/resume_session.

Body: ``{session_id: str, working_dir?: str, a0_ctx_id?: str}``.
Resumes a jcode session and returns a small history summary.
"""

from __future__ import annotations

import os

from helpers.api import ApiHandler, Request

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


class ResumeSession(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        session_id = (input or {}).get("session_id")
        if not session_id:
            return {"ok": False, "error": "session_id required"}
        wd = os.path.abspath((input or {}).get("working_dir") or os.getcwd())
        bin_path = locate_jcode_binary()
        if not bin_path:
            return {"ok": False, "error": "jcode not installed"}
        sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
        try:
            sock = await sup.ensure_running(wd)
        except NoCredentialsError as e:
            return {"ok": False, "error": str(e)}
        a0_ctx_id = (input or {}).get("a0_ctx_id") or "default"
        cid = get_or_create_client_instance_id(a0_ctx_id)
        client = JcodeClient()
        await client.connect(sock)
        try:
            await client.subscribe(
                wd, session_id, cid, allow_session_takeover=True
            )
            history_ev = await client._recv_until(
                lambda e: e.type == "history"
            )
            return {
                "ok": True,
                "session_id": session_id,
                "messages": len(getattr(history_ev, "messages", [])),
                "provider_session_id": getattr(
                    history_ev, "provider_session_id", None
                ),
            }
        finally:
            await client.close()
