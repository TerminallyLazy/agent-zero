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
from usr.plugins.jcode_harness.helpers.protocol import (
    Done,
    SessionId,
    TextDelta,
    UnknownEvent,
)


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


# ---------------------------------------------------------------------------
# Request method tests (Task 3.5)
# ---------------------------------------------------------------------------


async def _drain_n_lines(daemon, n: int):
    """Connect a client + collect ``n`` request lines from the fake daemon."""

    async def script(daemon, reader, writer):
        for _ in range(n):
            line = await reader.readline()
            if not line:
                return
            daemon.received_lines.append(line)

    daemon._script = script  # rebind script before .start() is called by caller
    return daemon


async def _make_collecting_daemon(n_lines: int) -> _FakeDaemon:
    async def script(d, reader, writer):
        for _ in range(n_lines):
            line = await reader.readline()
            if not line:
                return
            d.received_lines.append(line)

    daemon = _FakeDaemon(script)
    await daemon.start()
    return daemon


async def test_send_message_emits_message_request():
    daemon = await _make_collecting_daemon(1)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        rid = await client.send_message("hello", images=[("png", "abc")], msg_id=42)
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    assert rid == 42
    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "message"
    assert obj["id"] == 42
    assert obj["content"] == "hello"
    assert obj["images"] == [["png", "abc"]]


async def test_send_message_assigns_id_when_omitted():
    daemon = await _make_collecting_daemon(2)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        rid1 = await client.send_message("a")
        rid2 = await client.send_message("b")
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    assert rid2 == rid1 + 1


async def test_soft_interrupt_emits_correct_request():
    daemon = await _make_collecting_daemon(1)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        await client.soft_interrupt("stop now", urgent=True)
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "soft_interrupt"
    assert obj["content"] == "stop now"
    assert obj["urgent"] is True


async def test_cancel_soft_interrupts_emits_request():
    daemon = await _make_collecting_daemon(1)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        await client.cancel_soft_interrupts()
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "cancel_soft_interrupts"
    assert isinstance(obj["id"], int)


async def test_cancel_emits_request():
    daemon = await _make_collecting_daemon(1)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        await client.cancel()
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "cancel"


async def test_background_tool_emits_request():
    daemon = await _make_collecting_daemon(1)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        rid = await client.background_tool()
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "background_tool"
    assert obj["id"] == rid


async def test_stdin_response_emits_request():
    daemon = await _make_collecting_daemon(1)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        await client.stdin_response(request_id="rq-1", input="yes\n")
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "stdin_response"
    assert obj["request_id"] == "rq-1"
    assert obj["input"] == "yes\n"


async def test_resume_session_emits_request_with_takeover_true_default():
    daemon = await _make_collecting_daemon(1)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        await client.resume_session(session_id="fox-9", client_instance_id="iid")
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "resume_session"
    assert obj["session_id"] == "fox-9"
    assert obj["client_instance_id"] == "iid"
    assert obj["allow_session_takeover"] is True


async def test_ping_emits_request():
    daemon = await _make_collecting_daemon(1)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        await client.ping()
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "ping"


async def test_get_history_emits_request():
    daemon = await _make_collecting_daemon(1)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        await client.get_history()
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    obj = json.loads(daemon.received_lines[0])
    assert obj["type"] == "get_history"


async def test_id_counter_increments_across_method_types():
    daemon = await _make_collecting_daemon(4)
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        await client.ping()
        await client.cancel()
        await client.get_history()
        await client.cancel_soft_interrupts()
        await asyncio.sleep(0.01)
        await client.close()
    finally:
        await daemon.stop()

    ids = [json.loads(line)["id"] for line in daemon.received_lines]
    assert ids == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# events() async generator tests (Task 3.6)
# ---------------------------------------------------------------------------


async def _make_emitting_daemon(payloads: list[bytes]) -> _FakeDaemon:
    """Build a fake daemon that immediately emits ``payloads`` then closes."""

    async def script(d, reader, writer):
        for p in payloads:
            writer.write(p)
            await writer.drain()
        # Close write-side so client sees EOF.
        writer.close()

    daemon = _FakeDaemon(script)
    await daemon.start()
    return daemon


async def test_events_iterates_until_daemon_closes():
    daemon = await _make_emitting_daemon(
        [
            b'{"type":"text_delta","text":"a"}\n',
            b'{"type":"text_delta","text":"b"}\n',
            b'{"type":"text_delta","text":"c"}\n',
        ]
    )
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        seen = []
        async for ev in client.events():
            seen.append(ev)
        await client.close()
    finally:
        await daemon.stop()

    assert len(seen) == 3
    assert [e.text for e in seen] == ["a", "b", "c"]


async def test_events_yields_typed_dataclasses():
    daemon = await _make_emitting_daemon(
        [
            b'{"type":"text_delta","text":"hi"}\n',
            b'{"type":"done","id":7}\n',
        ]
    )
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        seen = [ev async for ev in client.events()]
        await client.close()
    finally:
        await daemon.stop()

    assert isinstance(seen[0], TextDelta)
    assert isinstance(seen[1], Done)


async def test_events_yields_unknown_event_for_new_variant():
    daemon = await _make_emitting_daemon(
        [b'{"type":"future_variant","x":42}\n']
    )
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        seen = [ev async for ev in client.events()]
        await client.close()
    finally:
        await daemon.stop()

    assert len(seen) == 1
    assert isinstance(seen[0], UnknownEvent)
    assert seen[0].raw == {"type": "future_variant", "x": 42}


async def test_events_skips_malformed_json_line():
    daemon = await _make_emitting_daemon(
        [
            b"not-valid-json\n",
            b'{"type":"text_delta","text":"good"}\n',
        ]
    )
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        seen = [ev async for ev in client.events()]
        await client.close()
    finally:
        await daemon.stop()

    assert len(seen) == 1
    assert isinstance(seen[0], TextDelta)
    assert seen[0].text == "good"


async def test_events_handles_done_event():
    daemon = await _make_emitting_daemon([b'{"type":"done","id":99}\n'])
    try:
        client = JcodeClient()
        await client.connect(daemon.socket_path)
        seen = [ev async for ev in client.events()]
        await client.close()
    finally:
        await daemon.stop()

    assert len(seen) == 1
    assert isinstance(seen[0], Done)
    assert seen[0].id == 99


# ---------------------------------------------------------------------------
# Reconnect + Reloading event tests (Task 3.7)
# ---------------------------------------------------------------------------


from usr.plugins.jcode_harness.helpers.protocol import Reloading, UnknownEvent  # noqa: E402


async def _start_subscribe_emit_close_daemon(
    socket_path: str, payloads_after_subscribe: list[bytes]
) -> _FakeDaemon:
    """Daemon variant that accepts a Subscribe, emits a SessionId, then emits
    ``payloads_after_subscribe`` and closes the connection.
    """

    async def script(d, reader, writer):
        await reader.readline()  # subscribe request
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        for p in payloads_after_subscribe:
            writer.write(p)
            await writer.drain()
        writer.close()

    daemon = _FakeDaemon(script)
    daemon.socket_path = socket_path

    # Start a server explicitly at the given path so we can re-bind later.
    async def _handle(reader, writer):
        try:
            await daemon._script(daemon, reader, writer)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    daemon._server = await asyncio.start_unix_server(_handle, path=socket_path)
    return daemon


async def _stop_daemon_keep_dir(daemon: _FakeDaemon) -> None:
    """Stop a daemon but leave the parent tempdir intact so a second daemon
    can rebind at the same path."""
    if daemon._server is not None:
        daemon._server.close()
        await daemon._server.wait_closed()
    try:
        os.unlink(daemon.socket_path)
    except OSError:
        pass


async def test_reconnect_on_eof():
    """Server 1 emits one text_delta then EOF (and stops listening). A second
    server at the same path emits another text_delta + done. The client must
    transparently reconnect, resubscribe, and yield both deltas."""
    tmpdir = tempfile.mkdtemp(prefix="jc-rc-")
    sock = str(Path(tmpdir) / "s")

    # daemon1 — handles exactly one connection then closes its listener so the
    # client's reconnect attempt fails until daemon2 takes over.
    daemon1_holder: dict = {}

    async def script1(d, reader, writer):
        await reader.readline()  # subscribe
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        writer.write(b'{"type":"text_delta","text":"first"}\n')
        await writer.drain()
        # Stop the listener so the client's reconnect can't re-hit daemon1.
        srv = daemon1_holder.get("server")
        if srv is not None:
            srv.close()
        writer.close()

    daemon1 = _FakeDaemon(script1)
    daemon1.socket_path = sock

    async def _h1(reader, writer):
        try:
            await daemon1._script(daemon1, reader, writer)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    daemon1._server = await asyncio.start_unix_server(_h1, path=sock)
    daemon1_holder["server"] = daemon1._server

    client = JcodeClient()
    client._reconnect_max_delay = 0.1  # keep the test fast
    await client.connect(sock)
    await client.subscribe(
        working_dir="/w",
        target_session_id=None,
        client_instance_id="iid",
    )

    seen: list = []

    async def collect():
        async for ev in client.events():
            seen.append(ev)
            if len(seen) >= 2:
                return

    collector = asyncio.create_task(collect())

    # Give the client time to read first delta and hit EOF.
    await asyncio.sleep(0.15)
    # Wait for daemon1 server to fully close (script1 closed it); then unlink
    # the socket file so daemon2 can rebind at the same path.
    await daemon1._server.wait_closed()
    try:
        os.unlink(sock)
    except OSError:
        pass

    # Bring up a second server at the same path that satisfies the
    # post-reconnect Subscribe + emits two more events.
    daemon2 = await _start_subscribe_emit_close_daemon(
        sock,
        [
            b'{"type":"text_delta","text":"second"}\n',
            b'{"type":"done","id":1}\n',
        ],
    )

    try:
        await asyncio.wait_for(collector, timeout=10.0)
    finally:
        await client.close()
        await _stop_daemon_keep_dir(daemon2)
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass

    assert len(seen) >= 2
    texts = [getattr(e, "text", None) for e in seen]
    assert texts == ["first", "second"]


async def test_reloading_event_switches_socket_and_resubscribes():
    """First server emits a Reloading event pointing at a new socket path.
    Client follows the reload, resubscribes on the new path, and yields the
    text_delta from the second server. Reloading itself is never yielded."""
    tmpdir = tempfile.mkdtemp(prefix="jc-rl-")
    sock1 = str(Path(tmpdir) / "s1")
    sock2 = str(Path(tmpdir) / "s2")

    async def script1(d, reader, writer):
        await reader.readline()  # subscribe
        writer.write(b'{"type":"session","session_id":"x"}\n')
        await writer.drain()
        writer.write(
            (
                '{"type":"reloading","new_socket":"' + sock2 + '"}\n'
            ).encode()
        )
        await writer.drain()
        # Hold open briefly, then close.
        await asyncio.sleep(0.05)

    daemon1 = _FakeDaemon(script1)
    daemon1.socket_path = sock1

    async def _h1(reader, writer):
        try:
            await daemon1._script(daemon1, reader, writer)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    daemon1._server = await asyncio.start_unix_server(_h1, path=sock1)

    daemon2 = await _start_subscribe_emit_close_daemon(
        sock2,
        [
            b'{"type":"text_delta","text":"after-reload"}\n',
            b'{"type":"done","id":1}\n',
        ],
    )

    client = JcodeClient()
    client._reconnect_max_delay = 0.05
    await client.connect(sock1)
    await client.subscribe(
        working_dir="/w",
        target_session_id=None,
        client_instance_id="iid",
    )

    seen: list = []
    try:
        async def collect():
            async for ev in client.events():
                seen.append(ev)
                if any(isinstance(e, Done) for e in seen):
                    return

        await asyncio.wait_for(collect(), timeout=10.0)
    finally:
        await client.close()
        await _stop_daemon_keep_dir(daemon1)
        await _stop_daemon_keep_dir(daemon2)
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass

    # Reloading event must NOT be yielded to consumers.
    assert not any(isinstance(e, Reloading) for e in seen)
    # Must include the text_delta from the new socket.
    assert any(
        isinstance(e, TextDelta) and e.text == "after-reload" for e in seen
    )


async def test_reloading_event_with_missing_field_falls_back_to_current_socket():
    """A Reloading event with no new_socket/socket field should not crash —
    the client closes and reopens the same socket and resubscribes."""
    tmpdir = tempfile.mkdtemp(prefix="jc-rlm-")
    sock = str(Path(tmpdir) / "s")

    state = {"connection": 0}

    async def script(d, reader, writer):
        state["connection"] += 1
        await reader.readline()  # subscribe
        writer.write(b'{"type":"session","session_id":"x"}\n')
        await writer.drain()
        if state["connection"] == 1:
            # First connection: emit reloading with NO new_socket/socket key,
            # then close so client reconnects.
            writer.write(b'{"type":"reloading"}\n')
            await writer.drain()
            await asyncio.sleep(0.05)
        else:
            # Second connection: deliver one event and shut down.
            writer.write(b'{"type":"text_delta","text":"ok"}\n')
            await writer.drain()
            writer.write(b'{"type":"done","id":1}\n')
            await writer.drain()

    daemon = _FakeDaemon(script)
    daemon.socket_path = sock

    async def _handle(reader, writer):
        try:
            await daemon._script(daemon, reader, writer)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    daemon._server = await asyncio.start_unix_server(_handle, path=sock)

    client = JcodeClient()
    client._reconnect_max_delay = 0.05
    await client.connect(sock)
    await client.subscribe(
        working_dir="/w",
        target_session_id=None,
        client_instance_id="iid",
    )

    seen: list = []
    try:
        async def collect():
            async for ev in client.events():
                seen.append(ev)
                if any(isinstance(e, Done) for e in seen):
                    return

        await asyncio.wait_for(collect(), timeout=10.0)
    finally:
        await client.close()
        await _stop_daemon_keep_dir(daemon)
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass

    assert state["connection"] == 2
    assert not any(isinstance(e, Reloading) for e in seen)
    assert any(isinstance(e, TextDelta) and e.text == "ok" for e in seen)


async def test_extract_reloading_socket_prefers_new_socket_over_socket():
    """Unit test on the defensive lookup helper directly."""
    client = JcodeClient()

    class _Ev:
        type = "reloading"

        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    # new_socket wins over socket.
    ev = _Ev(new_socket="/a", socket="/b")
    assert client._extract_reloading_socket(ev) == "/a"

    # falls back to socket if new_socket is missing.
    ev = _Ev(socket="/b")
    assert client._extract_reloading_socket(ev) == "/b"

    # raw dict path.
    ev = UnknownEvent(raw={"type": "reloading", "new_socket": "/c"})
    assert client._extract_reloading_socket(ev) == "/c"

    # nothing usable.
    ev = _Ev()
    assert client._extract_reloading_socket(ev) is None


async def test_reconnect_caps_at_max_delay(monkeypatch):
    """With socket missing, reconnect must back off, doubling each time, and
    cap at ``_reconnect_max_delay``. We patch ``asyncio.sleep`` to record the
    sequence without actually waiting."""
    import usr.plugins.jcode_harness.helpers.jcode_client as jc_mod

    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)
        # Bail out after a few iterations so the test terminates.
        if len(sleeps) >= 6:
            raise RuntimeError("stop-loop")

    client = JcodeClient()
    client._socket_path = "/nonexistent/path-for-test.sock"
    client._last_subscribe = ("/w", None, "iid", False)
    client._reconnect_max_delay = 4.0  # small cap so we hit it quickly

    monkeypatch.setattr(jc_mod.asyncio, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="stop-loop"):
        await client._reconnect()

    # Expected schedule: 1, 2, 4, 4, 4, 4 — capped at 4.0.
    assert sleeps[:3] == [1.0, 2.0, 4.0]
    assert all(s == 4.0 for s in sleeps[2:])
