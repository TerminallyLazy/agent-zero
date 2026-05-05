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
import json
import platform
import sys
from typing import AsyncIterator

from usr.plugins.jcode_harness.helpers.protocol import (
    BackgroundTool,
    Cancel,
    CancelSoftInterrupts,
    GetHistory,
    Message,
    Ping,
    ResumeSession,
    ServerEvent,
    SessionId,
    SoftInterrupt,
    StdinResponse,
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
        # Reconnect state — populated on first subscribe(); _reconnect() replays
        # the same args after EOF or after a Reloading event.
        self._last_subscribe: tuple[str, str | None, str, bool] | None = None
        self._reconnect_max_delay: float = 30.0

    async def connect(self, socket_path: str) -> None:
        """Open a connection to ``socket_path``.

        POSIX uses ``asyncio.open_unix_connection``. Windows delegates to the
        named-pipe transport stub
        :mod:`usr.plugins.jcode_harness.helpers.transport_windows`, which today
        raises :class:`NotImplementedError`; full pipe support (per spec §8.4)
        lands in v1.1. WSL2 is the recommended Windows path until then.
        """
        if platform.system() == "Windows":
            from usr.plugins.jcode_harness.helpers.transport_windows import (
                open_named_pipe,
            )
            self._reader, self._writer = await open_named_pipe(socket_path)
        else:
            self._reader, self._writer = await asyncio.open_unix_connection(
                socket_path
            )
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
        # Record args so _reconnect() can replay subscription verbatim after
        # EOF or after following a Reloading event to a new socket path.
        self._last_subscribe = (
            working_dir,
            target_session_id,
            client_instance_id,
            allow_session_takeover,
        )
        return ev  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Request methods (one per Request variant the harness emits)
    # ------------------------------------------------------------------

    async def send_message(
        self,
        content: str,
        images: list[tuple[str, str]] | None = None,
        msg_id: int | None = None,
    ) -> int:
        """Emit a ``message`` request. Returns the assigned id."""
        req_id = msg_id if msg_id is not None else self._next_id()
        await self._send(Message(id=req_id, content=content, images=images or []))
        return req_id

    async def soft_interrupt(
        self,
        content: str,
        urgent: bool = False,
        msg_id: int | None = None,
    ) -> int:
        """Inject a soft interrupt at the next safe point. Returns the id."""
        req_id = msg_id if msg_id is not None else self._next_id()
        await self._send(SoftInterrupt(id=req_id, content=content, urgent=urgent))
        return req_id

    async def cancel_soft_interrupts(self) -> None:
        """Drop any queued but undelivered soft interrupts on the server."""
        await self._send(CancelSoftInterrupts(id=self._next_id()))

    async def cancel(self) -> None:
        """Hard-cancel the current generation."""
        await self._send(Cancel(id=self._next_id()))

    async def background_tool(self, request_id: int | None = None) -> int:
        """Move the currently executing tool to background.

        Per ``jcode/crates/jcode-protocol/src/lib.rs:87`` the BackgroundTool
        variant carries a single ``id: u64`` field, which the server treats as
        an opaque request id (see ``Request::request_id_for`` line 1337). The
        request always backgrounds the *currently executing* tool — it does
        not target a specific tool by id. We therefore allocate a monotonic
        request id by default and let callers override only for tests.
        """
        req_id = request_id if request_id is not None else self._next_id()
        await self._send(BackgroundTool(id=req_id))
        return req_id

    async def stdin_response(self, request_id: str, input: str) -> None:
        """Reply to a daemon-issued ``stdin_request``."""
        await self._send(
            StdinResponse(id=self._next_id(), request_id=request_id, input=input)
        )

    async def resume_session(
        self,
        session_id: str,
        client_instance_id: str,
        allow_session_takeover: bool = True,
    ) -> None:
        """Resume an existing session by id."""
        await self._send(
            ResumeSession(
                id=self._next_id(),
                session_id=session_id,
                client_instance_id=client_instance_id,
                client_has_local_history=False,
                allow_session_takeover=allow_session_takeover,
            )
        )

    async def ping(self) -> None:
        """Liveness probe; daemon replies with a Pong event."""
        await self._send(Ping(id=self._next_id()))

    async def get_history(self) -> None:
        """Request the full session history snapshot."""
        await self._send(GetHistory(id=self._next_id()))

    async def _reconnect(self) -> None:
        """Reconnect to ``self._socket_path`` with exponential backoff and
        replay the last Subscribe args. Called on EOF or after a Reloading
        event.

        Backoff schedule: 1s → 2s → 4s … capped at ``self._reconnect_max_delay``
        (default 30s; tests may override). Loop continues until the connect +
        subscribe pair both succeed; callers cannot opt out — once a client has
        subscribed, the harness owns recovery.
        """
        if self._socket_path is None or self._last_subscribe is None:
            raise ConnectionError("cannot reconnect: never subscribed")
        delay = 1.0
        while True:
            try:
                await self.connect(self._socket_path)
                wd, target_sid, cid, allow = self._last_subscribe
                await self.subscribe(wd, target_sid, cid, allow)
                return
            except (ConnectionRefusedError, FileNotFoundError, ConnectionError, OSError):
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._reconnect_max_delay)

    def _extract_reloading_socket(self, ev) -> str | None:
        """Defensive lookup for the new socket path on a Reloading event.

        The exact field name is unverified (Spike 0.1 deferred); we try
        ``new_socket`` then ``socket`` on the dataclass, then fall back to the
        ``raw`` dict on :class:`UnknownEvent`-style payloads. ``None`` means
        the caller should reuse the current socket path.
        """
        for attr in ("new_socket", "socket"):
            v = getattr(ev, attr, None)
            if isinstance(v, str) and v:
                return v
        raw = getattr(ev, "raw", None)
        if isinstance(raw, dict):
            for k in ("new_socket", "socket"):
                v = raw.get(k)
                if isinstance(v, str) and v:
                    return v
        return None

    async def _follow_reloading(self, ev) -> bool:
        """If ``ev`` is a Reloading event, switch socket and resubscribe.

        Returns ``True`` if the reload was followed (caller must NOT yield this
        event to its consumer). ``False`` means it was not a reloading event.
        """
        if ev.type != "reloading":
            return False
        new_path = self._extract_reloading_socket(ev) or self._socket_path
        await self.close()
        await asyncio.sleep(0.1)
        self._socket_path = new_path
        await self._reconnect()
        return True

    async def events(self) -> AsyncIterator[ServerEvent]:
        """Yield decoded ServerEvent dataclasses until the daemon closes.

        Per the spec's forward-compat clause (§7.2), unknown event types fall
        through to :class:`UnknownEvent` (handled inside :func:`decode_event`).
        Lines that fail JSON parsing are logged to stderr and skipped so a
        single corrupt frame can't kill the event loop.

        On socket EOF mid-iteration we transparently reconnect (exponential
        backoff, last-Subscribe replay) and continue yielding. On a Reloading
        event we follow the new socket path, resubscribe, and resume — the
        Reloading event itself is consumed and never yielded.
        """
        assert self._reader is not None, "connect() must be called before events()"
        while True:
            try:
                line = await self._reader.readline()
            except ConnectionError:
                # Reader raised mid-iteration — reconnect and resume.
                await self._reconnect()
                continue
            if not line:
                # EOF. If we have subscribe state, treat as a transient
                # disconnect and reconnect; otherwise we're truly done.
                if self._last_subscribe is None or self._socket_path is None:
                    return
                await self._reconnect()
                continue
            try:
                ev = decode_event(line)
            except json.JSONDecodeError:
                print(
                    f"[jcode_harness.client] malformed JSON line skipped: "
                    f"{line[:80]!r}",
                    file=sys.stderr,
                )
                continue
            # Reloading is handled internally — never surfaced to the consumer.
            if await self._follow_reloading(ev):
                continue
            yield ev

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
