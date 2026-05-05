"""Unit tests for :class:`JcodeGrep`."""

from __future__ import annotations

import json

import pytest

from usr.plugins.jcode_harness.helpers.daemon import NoCredentialsError
from usr.plugins.jcode_harness.tools.jcode_grep import JcodeGrep
from usr.plugins.jcode_harness.tests.unit.conftest import make_tool, read_line


pytestmark = pytest.mark.asyncio


async def test_grep_returns_agentgrep_output(
    fake_agent, fake_daemon, patch_supervisor
):
    async def script(daemon, reader, writer):
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        msg_line = await read_line(reader)
        msg_id = json.loads(msg_line)["id"]
        writer.write(
            b'{"type":"tool_done","id":"t1","name":"agentgrep",'
            b'"output":"match1\\nmatch2"}\n'
        )
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeGrep, fake_agent)
    resp = await tool.execute(pattern="foo", path="/tmp")
    assert "match1" in resp.message
    assert "match2" in resp.message


async def test_grep_empty_pattern_returns_error_response(fake_agent):
    tool = make_tool(JcodeGrep, fake_agent)
    resp = await tool.execute(pattern="", path="/tmp")
    assert "pattern required" in resp.message
    assert resp.break_loop is False


async def test_grep_no_matches_returns_no_matches_message(
    fake_agent, fake_daemon, patch_supervisor
):
    async def script(daemon, reader, writer):
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"s1"}\n')
        await writer.drain()
        msg_line = await read_line(reader)
        msg_id = json.loads(msg_line)["id"]
        # Daemon runs agentgrep but it produces no output — emit tool_done
        # with empty output, then done. Tool should fall through to "no
        # matches" branch.
        writer.write(
            b'{"type":"tool_done","id":"t1","name":"agentgrep","output":""}\n'
        )
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeGrep, fake_agent)
    resp = await tool.execute(pattern="foo", path="/tmp")
    assert resp.message == "(no matches)"


async def test_grep_no_binary_returns_friendly_message(
    fake_agent, patch_supervisor
):
    patch_supervisor(None, binary=None)
    tool = make_tool(JcodeGrep, fake_agent)
    resp = await tool.execute(pattern="foo", path="/tmp")
    assert "not installed" in resp.message
    assert resp.break_loop is False


async def test_grep_no_creds_returns_friendly_message(
    fake_agent, patch_supervisor
):
    patch_supervisor(None, raises=NoCredentialsError("no providers"))
    tool = make_tool(JcodeGrep, fake_agent)
    resp = await tool.execute(pattern="foo", path="/tmp")
    assert "no providers" in resp.message


async def test_grep_uses_fresh_uuid_for_each_call(
    fake_agent, fake_daemon, patch_supervisor
):
    """Two grep calls must mint distinct client_instance_ids (one-shot tool)."""
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

    for _ in range(2):
        daemon = fake_daemon(script)
        sock = await daemon.start()
        patch_supervisor(sock)
        tool = make_tool(JcodeGrep, fake_agent)
        await tool.execute(pattern="foo", path="/tmp")

    assert len(seen_cids) == 2
    assert seen_cids[0] != seen_cids[1]
