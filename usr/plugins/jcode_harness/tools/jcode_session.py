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
    DaemonSpawnError,
    DaemonSupervisor,
    NoCredentialsError,
    locate_jcode_binary,
)
from usr.plugins.jcode_harness.helpers.jcode_client import (
    JcodeClient,
    DaemonProtocolError,
)
from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
from usr.plugins.jcode_harness.helpers.persistence import (
    get_or_create_client_instance_id,
)


# Polling interval (seconds) for the cancel-signal watcher. Module-level so
# tests can monkeypatch a faster value without exercising real-time delays.
_CANCEL_POLL_INTERVAL = 0.5

# Maximum time to wait for the daemon to emit any event after a message is sent.
# jcode normally emits ack/status/tool/text/done events. Silence beyond this
# point usually means the daemon is blocked waiting on provider, stdin, or an
# internal error path that did not surface as a protocol event.
_EVENT_IDLE_TIMEOUT = 300.0

# How long to wait for the daemon to respond to subscribe / send_message.
# These should be fast round-trips; a 30s ceiling catches broken daemons
# that accept the connection but never reply.
_HANDSHAKE_TIMEOUT = 30.0


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
        await self.set_progress("jcode coding harness active…")

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
        except DaemonSpawnError as e:
            # Surface jcode's own log tail so the operator (and the model
            # in the next turn) can see what went wrong without having to
            # SSH into the container. Repair path is documented in the
            # plugin troubleshooting guide.
            return Response(
                message=(
                    "jcode daemon failed to start.\n\n"
                    f"{e}\n\n"
                    "Repair: Plugins → jcode harness → Execute, or fix the "
                    "config issue shown in the log above and try again."
                ),
                break_loop=False,
            )

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
            await asyncio.wait_for(
                client.subscribe(
                    wd, resume_session_id, cid, allow_session_takeover=True
                ),
                timeout=_HANDSHAKE_TIMEOUT,
            )
        except (asyncio.TimeoutError, ConnectionError) as exc:
            watcher.cancel()
            await client.close()
            return Response(
                message=(
                    f"jcode daemon did not respond to subscribe within "
                    f"{int(_HANDSHAKE_TIMEOUT)}s: {exc}. "
                    "The daemon may be stuck. Retry the task or restart the "
                    "daemon via Plugins → jcode harness → Execute."
                ),
                break_loop=False,
            )
        except DaemonProtocolError as exc:
            watcher.cancel()
            await client.close()
            return Response(
                message=f"jcode daemon rejected connection: {exc}",
                break_loop=False,
            )

        try:
            msg_id = await asyncio.wait_for(
                client.send_message(task), timeout=_HANDSHAKE_TIMEOUT
            )
        except (asyncio.TimeoutError, ConnectionError) as exc:
            watcher.cancel()
            await client.close()
            return Response(
                message=(
                    f"jcode daemon did not accept message within "
                    f"{int(_HANDSHAKE_TIMEOUT)}s: {exc}. "
                    "Retry the task or restart the daemon."
                ),
                break_loop=False,
            )

        try:
            events = client.events().__aiter__()
            while True:
                try:
                    ev = await asyncio.wait_for(
                        anext(events), timeout=_EVENT_IDLE_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    return Response(
                        message=(
                            "jcode session produced no daemon events for "
                            f"{int(_EVENT_IDLE_TIMEOUT)}s after the task was sent. "
                            "The daemon may be blocked on provider I/O, stdin, or an "
                            "internal wait path. Retry the task, check the jcode harness "
                            "daemon status, or run Plugins → jcode harness → Execute "
                            "to restart the daemon."
                        ),
                        break_loop=False,
                    )
                except StopAsyncIteration:
                    break
                except ConnectionError as exc:
                    return Response(
                        message=(
                            f"jcode daemon connection lost during session: {exc}. "
                            "The daemon may have crashed. Retry the task or "
                            "restart via Plugins → jcode harness → Execute."
                        ),
                        break_loop=False,
                    )

                t = ev.type
                if t == "ack":
                    continue
                elif t == "error":
                    msg = getattr(ev, "message", "jcode daemon returned an error")
                    retry = getattr(ev, "retry_after_secs", None)
                    suffix = f" Retry after {retry}s." if retry else ""
                    return Response(
                        message=f"jcode daemon error: {msg}.{suffix}",
                        break_loop=False,
                    )
                elif t == "text_delta":
                    final_text.append(ev.text)
                    await self.set_progress("".join(final_text))
                elif t == "text_replace":
                    final_text[:] = [ev.text]
                    await self.set_progress("".join(final_text))
                elif t == "connection_phase":
                    await self.set_progress(f"[jcode: {ev.phase}]")
                elif t == "status_detail":
                    await self.set_progress(ev.detail)
                elif t == "connection_type":
                    await self.set_progress(f"[jcode connection: {ev.connection}]")
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
                elif t == "stdin_request":
                    if getattr(ev, "is_password", False):
                        return Response(
                            message=(
                                "jcode requested password input from a tool. "
                                "Agent Zero cannot safely provide hidden input; "
                                "run the command manually or retry with a non-interactive command."
                            ),
                            break_loop=False,
                        )
                    await self.set_progress(
                        "[jcode requested stdin; sent an empty line]"
                    )
                    await client.stdin_response(ev.request_id, "")
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
