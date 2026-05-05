"""jcode_grep: short-lived session wrapper around jcode's agentgrep tool.

Each invocation opens a fresh session, asks the model to call ``agentgrep``
on the given pattern, and returns the raw concatenated agentgrep output.

Spec ref: §3 "1. Bounded sessions" + the agentgrep tool reference. Distinct
from :mod:`jcode_session` in that one-shot tools allocate a fresh
``client_instance_id`` per call (no resume) and never set
``allow_session_takeover`` — they're always brand-new sessions.
"""

from __future__ import annotations

import os
import uuid

from helpers.tool import Tool, Response

from usr.plugins.jcode_harness.helpers.daemon import (
    DaemonSupervisor,
    NoCredentialsError,
    locate_jcode_binary,
)
from usr.plugins.jcode_harness.helpers.jcode_client import JcodeClient
from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir


class JcodeGrep(Tool):
    """Search for ``pattern`` under ``path`` via jcode's agentgrep tool."""

    async def execute(
        self,
        pattern: str = "",
        path: str = ".",
        **_kwargs,
    ) -> Response:
        if not pattern:
            return Response(message="pattern required", break_loop=False)

        wd = os.path.abspath(path)
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

        client = JcodeClient()
        await client.connect(sock)
        try:
            await client.subscribe(
                wd,
                None,
                str(uuid.uuid4()),
                allow_session_takeover=False,
            )
            prompt = (
                f"Use the agentgrep tool to search for: {pattern}\n"
                "Return ONLY the raw agentgrep output. Do not summarize."
            )
            msg_id = await client.send_message(prompt)
            outputs: list[str] = []
            async for ev in client.events():
                t = ev.type
                if t == "tool_done" and getattr(ev, "name", "") == "agentgrep":
                    if getattr(ev, "output", ""):
                        outputs.append(ev.output)
                elif t == "interrupted":
                    break
                elif t == "done" and getattr(ev, "id", None) == msg_id:
                    break
            return Response(
                message="\n".join(outputs) or "(no matches)",
                break_loop=False,
            )
        finally:
            await client.close()
