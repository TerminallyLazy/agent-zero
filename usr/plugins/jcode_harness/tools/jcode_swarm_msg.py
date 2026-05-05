"""jcode_swarm_msg: send DM/broadcast/share/read messages to other agents
in the same jcode swarm. Wraps :class:`CommMessage`, :class:`CommShare`,
and :class:`CommRead` protocol requests.

Spec ref: §3 "Swarm coordination". Field shapes mirror
``jcode/crates/jcode-protocol/src/lib.rs`` (the ``Comm*`` Request variants).
"""

from __future__ import annotations

import os
import uuid

from helpers.tool import Tool, Response

from usr.plugins.jcode_harness.helpers.daemon import (
    DaemonSpawnError,
    DaemonSupervisor,
    NoCredentialsError,
    locate_jcode_binary,
)
from usr.plugins.jcode_harness.helpers.jcode_client import JcodeClient
from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
from usr.plugins.jcode_harness.helpers.protocol import (
    CommMessage,
    CommRead,
    CommShare,
)


_VALID_ACTIONS = {"dm", "broadcast", "share", "read"}


class JcodeSwarmMsg(Tool):
    """Coordinate with other jcode agents over the daemon's swarm channel."""

    async def execute(
        self,
        action: str = "",
        target: str | None = None,
        message: str = "",
        session_id: str | None = None,
        key: str = "",
        value: str = "",
        working_dir: str | None = None,
        **_kwargs,
    ) -> Response:
        action = action.lower().strip()
        if action not in _VALID_ACTIONS:
            return Response(
                message=(
                    f"action must be one of {sorted(_VALID_ACTIONS)}; "
                    f"got {action!r}"
                ),
                break_loop=False,
            )

        # Validate per-action required args before opening a connection.
        if action == "dm" and not target:
            return Response(
                message="dm requires target session id",
                break_loop=False,
            )
        if action == "share" and (not session_id or not key):
            return Response(
                message="share requires session_id and key",
                break_loop=False,
            )
        if action == "read" and not session_id:
            return Response(
                message="read requires session_id",
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
            await client.subscribe(
                wd, None, str(uuid.uuid4()), allow_session_takeover=False
            )
            req_id = client._next_id()
            if action == "dm":
                req = CommMessage(
                    id=req_id,
                    from_session="",
                    message=message,
                    to_session=target,
                )
            elif action == "broadcast":
                req = CommMessage(
                    id=req_id,
                    from_session="",
                    message=message,
                    to_session=None,
                )
            elif action == "share":
                req = CommShare(
                    id=req_id,
                    session_id=session_id or "",
                    key=key,
                    value=value,
                    append=False,
                )
            else:  # action == "read"
                req = CommRead(
                    id=req_id,
                    session_id=session_id or "",
                    key=key if key else None,
                )
            await client._send(req)
            return Response(
                message=f"swarm {action} sent (req_id={req_id})",
                break_loop=False,
            )
        finally:
            await client.close()
