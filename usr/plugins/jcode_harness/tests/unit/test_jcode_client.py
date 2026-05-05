"""Unit tests for :class:`JcodeClient`.

We stand up a minimal in-process Unix-socket server with
``asyncio.start_unix_server`` and exercise the client against it. The fake
server reads/writes the same NDJSON wire format the real jcode daemon uses,
so we get end-to-end transport coverage without spawning a Rust binary.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from usr.plugins.jcode_harness.helpers.jcode_client import JcodeClient
from usr.plugins.jcode_harness.helpers.protocol import SessionId


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fake daemon helpers
# ---------------------------------------------------------------------------


class _FakeDaemon:
    """A trivial Unix-socket NDJSON server that records every line it reads
    and emits whatever the test scripts via ``script``.

    ``script`` is an async callable ``(reader, writer) -> None`` that drives a
    single connection. Each daemon serves exactly one client.
    """

    def __init__(self, script):
        self._script = script
        self._server: asyncio.base_events.Server | None = None
        self.received_lines: list[bytes] = []
        self.socket_path: str = ""

    async def start(self) -> str:
        # Use a short tmp path; macOS sun_path is 104 bytes.
        tmpdir = tempfile.mkdtemp(prefix="jc-")
        self.socket_path = str(Path(tmpdir) / "s")

        async def _handle(reader, writer):
            try:
                await self._script(self, reader, writer)
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        self._server = await asyncio.start_unix_server(_handle, path=self.socket_path)
        return self.socket_path

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass
        try:
            os.rmdir(os.path.dirname(self.socket_path))
        except OSError:
            pass


async def _read_one_line(reader: asyncio.StreamReader) -> bytes:
    return await reader.readline()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_connect_to_unix_socket_succeeds():
    async def script(daemon, reader, writer):
        # Hold the connection open briefly so the client can complete connect().
        await asyncio.sleep(0.01)

    daemon = _FakeDaemon(script)
    sock = await daemon.start()
    try:
        client = JcodeClient()
        await client.connect(sock)
        assert client._writer is not None  # connection is live
        await client.close()
    finally:
        await daemon.stop()


async def test_subscribe_sends_correct_request():
    async def script(daemon, reader, writer):
        line = await _read_one_line(reader)
        daemon.received_lines.append(line)
        # Reply with a session event so subscribe() returns.
        writer.write(b'{"type":"session","session_id":"fox-1"}\n')
        await writer.drain()

    daemon = _FakeDaemon(script)
    sock = await daemon.start()
    try:
        client = JcodeClient()
        await client.connect(sock)
        await client.subscribe(
            working_dir="/work",
            target_session_id="prev-sess",
            client_instance_id="abc123",
            allow_session_takeover=True,
        )
        # Drain server task.
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    assert len(daemon.received_lines) == 1
    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "subscribe"
    assert obj["working_dir"] == "/work"
    assert obj["target_session_id"] == "prev-sess"
    assert obj["client_instance_id"] == "abc123"
    assert obj["allow_session_takeover"] is True
    assert obj["client_has_local_history"] is False
    assert isinstance(obj["id"], int) and obj["id"] >= 1


async def test_subscribe_returns_session_id_event():
    async def script(daemon, reader, writer):
        await _read_one_line(reader)
        writer.write(b'{"type":"session","session_id":"fox-1"}\n')
        await writer.drain()

    daemon = _FakeDaemon(script)
    sock = await daemon.start()
    try:
        client = JcodeClient()
        await client.connect(sock)
        ev = await client.subscribe(
            working_dir="/w",
            target_session_id=None,
            client_instance_id="iid",
        )
        assert isinstance(ev, SessionId)
        assert ev.session_id == "fox-1"
        await client.close()
    finally:
        await daemon.stop()


async def test_subscribe_raises_if_session_event_missing():
    async def script(daemon, reader, writer):
        # Read the request then close immediately without emitting session.
        await _read_one_line(reader)
        writer.close()

    daemon = _FakeDaemon(script)
    sock = await daemon.start()
    try:
        client = JcodeClient()
        await client.connect(sock)
        with pytest.raises(ConnectionError):
            await client.subscribe(
                working_dir="/w",
                target_session_id=None,
                client_instance_id="iid",
            )
        await client.close()
    finally:
        await daemon.stop()


async def test_close_is_idempotent():
    async def script(daemon, reader, writer):
        await asyncio.sleep(0.01)

    daemon = _FakeDaemon(script)
    sock = await daemon.start()
    try:
        client = JcodeClient()
        await client.connect(sock)
        await client.close()
        await client.close()  # second close must be a no-op
    finally:
        await daemon.stop()
