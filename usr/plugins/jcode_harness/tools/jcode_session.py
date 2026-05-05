"""jcode_session: opens a bounded jcode session and streams events back to A0.

Default tool for any non-trivial coding task in the jcode_coder profile. Holds
a single subscribe -> message exchange open until the daemon emits a matching
``done`` (or an ``interrupted``) event, surfacing text deltas as A0 progress
updates and warning the operator on auto-compaction.

Spec ref: §3 "1. Bounded sessions", §5.6, §6.1.
"""

from __future__ import annotations

import asyncio
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


# Polling interval (seconds) for the cancel-signal watcher. Module-level so
# tests can monkeypatch a faster value without exercising real-time delays.
_CANCEL_POLL_INTERVAL = 0.5


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

        # Map A0's single-stop cancel signal onto jcode's soft_interrupt.
        # ``streaming_agent`` is the A0 runtime hook for in-flight redirect;
        # the lookup is defensive (signal API may be absent in tests).
        cancel_signal = getattr(self.agent.context, "streaming_agent", None)

        async def _watch_for_cancel() -> None:
            if cancel_signal is None:
                return
            while True:
                await asyncio.sleep(_CANCEL_POLL_INTERVAL)
                if getattr(cancel_signal, "cancel_requested", False):
                    try:
                        await client.soft_interrupt(
                            content="user requested redirect", urgent=False
                        )
                        cancel_signal.cancel_requested = False
                    except Exception:
                        pass
                    return  # one shot per session; user can re-click

        watcher = asyncio.create_task(_watch_for_cancel())
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
                    # Push a structured log event that the right-canvas
                    # ``jcode_panel.js`` (Chunk 9) subscribes to. Until then
                    # this is just a recorded event on the agent log.
                    payload = {
                        "count": getattr(ev, "count", 0),
                        "prompt_chars": getattr(ev, "prompt_chars", 0),
                        "computed_age_ms": getattr(ev, "computed_age_ms", 0),
                    }
                    try:
                        self.agent.context.log.log(
                            type="memory_injected",
                            content=(
                                f"+{payload['count']} memories "
                                f"({payload['prompt_chars']} chars, "
                                f"{payload['computed_age_ms']}ms old)"
                            ),
                            kvps=payload,
                        )
                    except Exception:
                        # Log surface unavailable in test env; non-fatal.
                        pass
                elif t == "compaction":
                    notify.warning("jcode auto-compacted context")
                elif t == "interrupted":
                    break
                elif t == "done" and getattr(ev, "id", None) == msg_id:
                    break
            return Response(message="".join(final_text), break_loop=False)
        finally:
            watcher.cancel()
            try:
                await watcher
            except (asyncio.CancelledError, Exception):
                pass
            await client.close()
