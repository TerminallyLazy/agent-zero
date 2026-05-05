"""jcode_session: opens a bounded jcode session and streams events back to A0.

Default tool for any non-trivial coding task in the jcode_coder profile. Holds
a single subscribe -> message exchange open until the daemon emits a matching
``done`` (or an ``interrupted``) event, surfacing text deltas as A0 progress
updates and warning the operator on auto-compaction.

Spec ref: §3 "1. Bounded sessions", §5.6, §6.1.
"""

from __future__ import annotations

import os

from helpers.tool import Tool, Response

from usr.plugins.jcode_harness.helpers import notifications as notify
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


class JcodeSession(Tool):
    """Run a bounded jcode session for a single coding task and return its output."""

    async def execute(
        self,
        task: str = "",
        working_dir: str | None = None,
        resume_session_id: str | None = None,
        **_kwargs,
    ) -> Response:
        wd = os.path.abspath(working_dir or os.getcwd())

        bin_path = locate_jcode_binary()
        if not bin_path:
            return Response(
                message="jcode binary not installed; run plugin install.",
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
        final_text: list[str] = []
        try:
            await client.subscribe(
                wd, resume_session_id, cid, allow_session_takeover=True
            )
            msg_id = await client.send_message(task)
            async for ev in client.events():
                t = ev.type
                if t == "text_delta":
                    final_text.append(ev.text)
                    await self.set_progress("".join(final_text))
                elif t == "tool_start":
                    await self.set_progress(f"[running tool: {ev.name}]")
                elif t == "tool_done":
                    if getattr(ev, "error", None):
                        await self.set_progress(
                            f"[tool error: {ev.error[:100]}]"
                        )
                elif t == "memory_injected":
                    # 7.2.B will wire memory injection to the side panel; for
                    # now we just consume the event so it doesn't surface as
                    # text.
                    pass
                elif t == "compaction":
                    notify.warning("jcode auto-compacted context")
                elif t == "interrupted":
                    break
                elif t == "done" and getattr(ev, "id", None) == msg_id:
                    break
            return Response(message="".join(final_text), break_loop=False)
        finally:
            await client.close()
