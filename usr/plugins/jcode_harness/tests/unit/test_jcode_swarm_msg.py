"""Unit tests for :class:`JcodeSwarmMsg`."""

from __future__ import annotations

import asyncio
import json

import pytest

from usr.plugins.jcode_harness.helpers.daemon import NoCredentialsError
from usr.plugins.jcode_harness.tools.jcode_swarm_msg import JcodeSwarmMsg
from usr.plugins.jcode_harness.tests.unit.conftest import make_tool, read_line


pytestmark = pytest.mark.asyncio


def _subscribe_then_capture():
    """Build a fake-daemon script that ACKs subscribe, then captures the next
    request line into ``daemon.received_lines`` and ends. Sets the
    ``captured`` event so callers can ``await`` the capture.
    """

    async def script(daemon, reader, writer):
        # subscribe handshake
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        # next request = our comm_* payload
        line = await read_line(reader)
        daemon.received_lines.append(line)
        ev = getattr(daemon, "captured", None)
        if ev is not None:
            ev.set()

    return script


async def _await_capture(daemon, timeout: float = 1.0) -> None:
    ev = getattr(daemon, "captured", None)
    if ev is None:
        return
    await asyncio.wait_for(ev.wait(), timeout=timeout)


async def test_swarm_invalid_action_returns_error(fake_agent, patch_supervisor):
    patch_supervisor("/no/sock")
    tool = make_tool(JcodeSwarmMsg, fake_agent)
    resp = await tool.execute(action="bogus")
    assert "action must be one of" in resp.message


async def test_swarm_dm_requires_target(fake_agent, patch_supervisor):
    patch_supervisor("/no/sock")
    tool = make_tool(JcodeSwarmMsg, fake_agent)
    resp = await tool.execute(action="dm", message="hi")
    assert "target" in resp.message


async def test_swarm_share_requires_session_id_and_key(
    fake_agent, patch_supervisor
):
    patch_supervisor("/no/sock")
    tool = make_tool(JcodeSwarmMsg, fake_agent)
    resp = await tool.execute(action="share", value="v")
    assert "session_id" in resp.message and "key" in resp.message


async def test_swarm_read_requires_session_id(fake_agent, patch_supervisor):
    patch_supervisor("/no/sock")
    tool = make_tool(JcodeSwarmMsg, fake_agent)
    resp = await tool.execute(action="read")
    assert "session_id" in resp.message


async def test_swarm_dm_sends_comm_message_to_target(
    fake_agent, fake_daemon, patch_supervisor
):
    daemon = fake_daemon(_subscribe_then_capture())
    daemon.captured = asyncio.Event()
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeSwarmMsg, fake_agent)
    resp = await tool.execute(
        action="dm", target="peer-x", message="hello", working_dir="/tmp"
    )
    await _await_capture(daemon)
    assert "swarm dm sent" in resp.message
    assert daemon.received_lines, "no request captured"
    payload = json.loads(daemon.received_lines[0])
    assert payload["type"] == "comm_message"
    assert payload["to_session"] == "peer-x"
    assert payload["message"] == "hello"


async def test_swarm_broadcast_omits_to_session(
    fake_agent, fake_daemon, patch_supervisor
):
    daemon = fake_daemon(_subscribe_then_capture())
    daemon.captured = asyncio.Event()
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeSwarmMsg, fake_agent)
    await tool.execute(
        action="broadcast", message="all hands", working_dir="/tmp"
    )
    await _await_capture(daemon)
    payload = json.loads(daemon.received_lines[0])
    assert payload["type"] == "comm_message"
    assert payload.get("to_session") is None


async def test_swarm_share_sends_comm_share(
    fake_agent, fake_daemon, patch_supervisor
):
    daemon = fake_daemon(_subscribe_then_capture())
    daemon.captured = asyncio.Event()
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeSwarmMsg, fake_agent)
    await tool.execute(
        action="share",
        session_id="sess-1",
        key="k",
        value="v",
        working_dir="/tmp",
    )
    await _await_capture(daemon)
    payload = json.loads(daemon.received_lines[0])
    assert payload["type"] == "comm_share"
    assert payload["session_id"] == "sess-1"
    assert payload["key"] == "k"
    assert payload["value"] == "v"


async def test_swarm_read_sends_comm_read(
    fake_agent, fake_daemon, patch_supervisor
):
    daemon = fake_daemon(_subscribe_then_capture())
    daemon.captured = asyncio.Event()
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeSwarmMsg, fake_agent)
    await tool.execute(
        action="read", session_id="sess-1", key="k", working_dir="/tmp"
    )
    await _await_capture(daemon)
    payload = json.loads(daemon.received_lines[0])
    assert payload["type"] == "comm_read"
    assert payload["session_id"] == "sess-1"
    assert payload["key"] == "k"


async def test_swarm_no_binary(fake_agent, patch_supervisor):
    patch_supervisor(None, binary=None)
    tool = make_tool(JcodeSwarmMsg, fake_agent)
    resp = await tool.execute(action="broadcast", message="hi")
    assert "not installed" in resp.message


async def test_swarm_no_creds(fake_agent, patch_supervisor):
    patch_supervisor(None, raises=NoCredentialsError("no providers"))
    tool = make_tool(JcodeSwarmMsg, fake_agent)
    resp = await tool.execute(action="broadcast", message="hi")
    assert "no providers" in resp.message
