"""jcode_skill: short-lived session wrapper around jcode's skill_manage tool.

Drives the skill subsystem (per spec §3 #3) from A0. Each call opens a fresh
session, asks the model to dispatch ``skill_manage`` with the given action
(and optional skill name), and returns the raw output.

Supported actions: load | list | reload | reload_all | read.
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


_VALID_ACTIONS = frozenset({"load", "list", "reload", "reload_all", "read"})


class JcodeSkill(Tool):
    """Drive the jcode skill_manage tool from A0."""

    async def execute(
        self,
        action: str = "",
        name: str = "",
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
                f"Use the skill_manage tool with action={action}, "
                f"name={name!r}. Return the raw output."
            )
            msg_id = await client.send_message(prompt)
            outputs: list[str] = []
            events = client.events().__aiter__()
            while True:
                try:
                    ev = await asyncio.wait_for(anext(events), timeout=60.0)
                except asyncio.TimeoutError:
                    return Response(
                        message="jcode skill timed out (no events for 60s).",
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
                if t == "tool_done" and getattr(ev, "name", "") == "skill_manage":
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
