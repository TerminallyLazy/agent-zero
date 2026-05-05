"""Async NDJSON client for the jcode daemon.

Wraps a Unix-socket connection to the jcode daemon and exposes the subset of
:mod:`usr.plugins.jcode_harness.helpers.protocol` Request variants the harness
emits, plus an async iterator over decoded ServerEvent dataclasses.

The client is intentionally a thin transport: it serialises requests, reads
NDJSON lines, and yields typed events. Higher-level concerns (reconnection,
session-takeover policy, soft-interrupt sequencing) live in DaemonSupervisor
and the plugin tools.
"""

from __future__ import annotations

import asyncio
import platform

from usr.plugins.jcode_harness.helpers.protocol import (
    ServerEvent,
    SessionId,
    Subscribe,
    decode_event,
    encode_request,
)


class JcodeClient:
    """Single-connection async NDJSON client for the jcode daemon."""

    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._socket_path: str | None = None
        self._subscribed: bool = False
        self._id_counter: int = 0

    async def connect(self, socket_path: str) -> None:
        """Open a Unix-socket connection to ``socket_path``.

        On Windows the daemon exposes a named pipe; that transport is wired in
        Task 3.8. For now we raise ``NotImplementedError`` so callers fail loud
        rather than silently dropping to localhost TCP or similar.
        """
        if platform.system() == "Windows":
            raise NotImplementedError("Windows transport not yet implemented")
        self._reader, self._writer = await asyncio.open_unix_connection(socket_path)
        self._socket_path = socket_path

    async def _send(self, req) -> None:
        assert self._writer is not None, "connect() must be called before _send"
        self._writer.write(encode_request(req))
        await self._writer.drain()

    async def _recv_until(self, predicate) -> ServerEvent:
        assert self._reader is not None, "connect() must be called before _recv_until"
        while True:
            line = await self._reader.readline()
            if not line:
                raise ConnectionError("daemon closed connection")
            ev = decode_event(line)
            if predicate(ev):
                return ev

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    async def subscribe(
        self,
        working_dir: str,
        target_session_id: str | None,
        client_instance_id: str,
        allow_session_takeover: bool = False,
    ) -> SessionId:
        """Send a subscribe request and return the SessionId event from daemon."""
        req_id = self._next_id()
        req = Subscribe(
            id=req_id,
            working_dir=working_dir,
            target_session_id=target_session_id,
            client_instance_id=client_instance_id,
            client_has_local_history=False,
            allow_session_takeover=allow_session_takeover,
        )
        await self._send(req)
        ev = await self._recv_until(lambda e: e.type == "session")
        self._subscribed = True
        return ev  # type: ignore[return-value]

    async def close(self) -> None:
        """Idempotent close — safe to call multiple times."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        self._subscribed = False
