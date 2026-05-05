"""Unit tests for :class:`JcodeMemory`."""

from __future__ import annotations

import json

import pytest

from usr.plugins.jcode_harness.helpers.daemon import NoCredentialsError
from usr.plugins.jcode_harness.tools.jcode_memory import JcodeMemory
from usr.plugins.jcode_harness.tests.unit.conftest import make_tool, read_line


pytestmark = pytest.mark.asyncio


async def test_memory_remember_round_trip(
    fake_agent, fake_daemon, patch_supervisor
):
    payloads: list[str] = []

    async def script(daemon, reader, writer):
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        msg_line = await read_line(reader)
        payloads.append(json.loads(msg_line)["content"])
        msg_id = json.loads(msg_line)["id"]
        writer.write(
            b'{"type":"tool_done","id":"t1","name":"memory_manage",'
            b'"output":"ok"}\n'
        )
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeMemory, fake_agent)
    resp = await tool.execute(
        action="remember",
        scope="project",
        content="test note",
        working_dir="/tmp",
    )
    assert resp.message == "ok"
    assert "action=remember" in payloads[0]
    assert "scope=project" in payloads[0]
    assert "test note" in payloads[0]


async def test_memory_recall_with_query(
    fake_agent, fake_daemon, patch_supervisor
):
    payloads: list[str] = []

    async def script(daemon, reader, writer):
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        msg_line = await read_line(reader)
        payloads.append(json.loads(msg_line)["content"])
        msg_id = json.loads(msg_line)["id"]
        writer.write(
            b'{"type":"tool_done","id":"t1","name":"memory_manage",'
            b'"output":"hit-1\\nhit-2"}\n'
        )
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeMemory, fake_agent)
    resp = await tool.execute(
        action="recall",
        query="auth flow",
        working_dir="/tmp",
    )
    assert "hit-1" in resp.message
    assert "hit-2" in resp.message
    assert "action=recall" in payloads[0]
    assert "auth flow" in payloads[0]


async def test_memory_invalid_action_returns_error(fake_agent):
    tool = make_tool(JcodeMemory, fake_agent)
    resp = await tool.execute(action="bogus", working_dir="/tmp")
    assert "invalid action" in resp.message
    assert "bogus" in resp.message
    assert resp.break_loop is False


async def test_memory_no_binary_returns_friendly_message(
    fake_agent, patch_supervisor
):
    patch_supervisor(None, binary=None)
    tool = make_tool(JcodeMemory, fake_agent)
    resp = await tool.execute(action="remember", content="x", working_dir="/tmp")
    assert "not installed" in resp.message


async def test_memory_no_creds_returns_friendly_message(
    fake_agent, patch_supervisor
):
    patch_supervisor(None, raises=NoCredentialsError("no providers"))
    tool = make_tool(JcodeMemory, fake_agent)
    resp = await tool.execute(action="recall", query="x", working_dir="/tmp")
    assert "no providers" in resp.message
