"""Unit tests for :class:`JcodeSession`."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from usr.plugins.jcode_harness.helpers.daemon import NoCredentialsError
from usr.plugins.jcode_harness.tools.jcode_session import JcodeSession
from usr.plugins.jcode_harness.tests.unit.conftest import make_tool, read_line


pytestmark = pytest.mark.asyncio


async def _run_session(tool, task: str = "go") -> str:
    """Drive ``JcodeSession.execute`` and return the response message."""
    resp = await tool.execute(task=task, working_dir="/tmp")
    return resp.message


async def test_session_returns_streamed_text(
    fake_agent, fake_daemon, patch_supervisor
):
    async def script(daemon, reader, writer):
        # subscribe
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        # message
        msg_line = await read_line(reader)
        msg_id = json.loads(msg_line)["id"]
        for chunk in (b"a", b"b", b"c"):
            writer.write(b'{"type":"text_delta","text":"' + chunk + b'"}\n')
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeSession, fake_agent)
    msg = await _run_session(tool, task="hi")
    assert msg == "abc"


async def test_session_no_binary_returns_friendly_message(
    fake_agent, patch_supervisor
):
    patch_supervisor(None, binary=None)
    tool = make_tool(JcodeSession, fake_agent)
    resp = await tool.execute(task="x", working_dir="/tmp")
    assert "not installed" in resp.message
    assert resp.break_loop is False


async def test_session_no_creds_returns_friendly_message(
    fake_agent, patch_supervisor
):
    patch_supervisor(None, raises=NoCredentialsError("no providers"))
    tool = make_tool(JcodeSession, fake_agent)
    resp = await tool.execute(task="x", working_dir="/tmp")
    assert "no providers" in resp.message
    assert resp.break_loop is False


async def test_session_breaks_on_interrupted_event(
    fake_agent, fake_daemon, patch_supervisor
):
    async def script(daemon, reader, writer):
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        await read_line(reader)
        writer.write(b'{"type":"text_delta","text":"partial"}\n')
        writer.write(b'{"type":"interrupted"}\n')
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeSession, fake_agent)
    resp = await tool.execute(task="hi", working_dir="/tmp")
    assert resp.message == "partial"
    assert resp.break_loop is False


async def test_session_calls_set_progress_for_tool_start(
    fake_agent, fake_daemon, patch_supervisor
):
    async def script(daemon, reader, writer):
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        msg_line = await read_line(reader)
        msg_id = json.loads(msg_line)["id"]
        writer.write(
            b'{"type":"tool_start","id":"t1","name":"agentgrep"}\n'
        )
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    progress_log: list[str] = []

    tool = make_tool(JcodeSession, fake_agent)

    async def _record(content):
        progress_log.append(content or "")
        tool.progress = content or ""

    tool.set_progress = _record  # type: ignore[assignment]

    await tool.execute(task="x", working_dir="/tmp")
    assert any("[running tool: agentgrep]" in p for p in progress_log)


async def test_session_warns_on_compaction(
    fake_agent, fake_daemon, patch_supervisor
):
    async def script(daemon, reader, writer):
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        msg_line = await read_line(reader)
        msg_id = json.loads(msg_line)["id"]
        writer.write(b'{"type":"compaction","trigger":"auto"}\n')
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeSession, fake_agent)
    with patch(
        "usr.plugins.jcode_harness.tools.jcode_session.notify.warning"
    ) as warn:
        await tool.execute(task="x", working_dir="/tmp")
    assert warn.called
    args, _ = warn.call_args
    assert "compact" in args[0].lower()


async def test_session_uses_persistent_client_instance_id(
    fake_agent, fake_daemon, patch_supervisor, tmp_path, monkeypatch
):
    """Two calls with the same a0 ctx id must reuse the same client_instance_id."""
    # Redirect amplihack root so persistence writes into a temp dir.
    monkeypatch.setenv("HOME", str(tmp_path))
    # Re-patch the path resolver: it captured Path.home() at import time.
    from usr.plugins.jcode_harness.helpers import paths as paths_mod

    monkeypatch.setattr(
        paths_mod, "amplihack_root", lambda: tmp_path / ".amplihack"
    )

    seen_cids: list[str] = []

    async def script(daemon, reader, writer):
        sub_line = await read_line(reader)
        seen_cids.append(json.loads(sub_line)["client_instance_id"])
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        msg_line = await read_line(reader)
        msg_id = json.loads(msg_line)["id"]
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    # Two separate daemons / sockets, but same fake_agent (same context.id).
    for _ in range(2):
        daemon = fake_daemon(script)
        sock = await daemon.start()
        patch_supervisor(sock)
        tool = make_tool(JcodeSession, fake_agent)
        await tool.execute(task="hi", working_dir=str(tmp_path))

    assert len(seen_cids) == 2
    assert seen_cids[0] == seen_cids[1]
