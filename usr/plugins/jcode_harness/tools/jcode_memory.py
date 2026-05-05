"""jcode_memory: short-lived session wrapper around jcode's memory_manage tool.

Exposes the memory subsystem (per spec §3 #2) as an A0 tool. Each call opens
a fresh session, asks the model to dispatch ``memory_manage`` with the given
action/scope/query/content, and returns the raw output the daemon yields.

Supported actions: remember | recall | search | forget | tag | link | related.
Default scope is ``project`` so a stored note lives with the working tree
rather than spilling into ``user``-scope memory.
"""

from __future__ import annotations

import asyncio
import os
import uuid

from helpers.tool import Tool, Response

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


_VALID_ACTIONS = frozenset(
    {"remember", "recall", "search", "forget", "tag", "link", "related"}
)


class JcodeMemory(Tool):
    """Drive the jcode memory_manage tool from A0."""

    async def execute(
        self,
        action: str = "",
        scope: str = "project",
        query: str = "",
        content: str = "",
        working_dir: str | None = None,
        **_kwargs,
    ) -> Response:
        if action not in _VALID_ACTIONS:
            return Response(
                message=(
                    f"invalid action {action!r}; expected one of "
                    f"{sorted(_VALID_ACTIONS)}"
                ),
                break_loop=False,
            )

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
        except DaemonSpawnError as e:
            return Response(
                message=(
                    "jcode daemon failed to start.\n\n"
                    f"{e}\n\n"
                    "Repair: Plugins → jcode harness → Execute."
                ),
                break_loop=False,
            )

        client = JcodeClient()
        await client.connect(sock)
        try:
            try:
                await asyncio.wait_for(
                    client.subscribe(
                        wd,
                        None,
                        str(uuid.uuid4()),
                        allow_session_takeover=False,
                    ),
                    timeout=30.0,
                )
            except (asyncio.TimeoutError, ConnectionError) as exc:
                return Response(
                    message=f"jcode daemon did not respond to subscribe: {exc}",
                    break_loop=False,
                )
            except DaemonProtocolError as exc:
                return Response(
                    message=f"jcode daemon rejected connection: {exc}",
                    break_loop=False,
                )
            prompt = (
                f"Use the memory_manage tool with action={action}, "
                f"scope={scope}, query={query!r}, content={content!r}. "
                "Return the raw output."
            )
            msg_id = await client.send_message(prompt)
            outputs: list[str] = []
            events = client.events().__aiter__()
            while True:
                try:
                    ev = await asyncio.wait_for(anext(events), timeout=60.0)
                except asyncio.TimeoutError:
                    return Response(
                        message="jcode memory timed out (no events for 60s).",
                        break_loop=False,
                    )
                except StopAsyncIteration:
                    break
                except ConnectionError as exc:
                    return Response(
                        message=f"jcode daemon connection lost: {exc}",
                        break_loop=False,
                    )
                t = ev.type
                if t == "tool_done" and getattr(ev, "name", "") == "memory_manage":
                    if getattr(ev, "output", ""):
                        outputs.append(ev.output)
                elif t == "interrupted":
                    break
                elif t == "done" and getattr(ev, "id", None) == msg_id:
                    break
            return Response(
                message="\n".join(outputs) or "(no output)",
                break_loop=False,
            )
        finally:
            await client.close()
