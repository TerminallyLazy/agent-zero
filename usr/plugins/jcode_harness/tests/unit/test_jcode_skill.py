"""Unit tests for :class:`JcodeSkill`."""

from __future__ import annotations

import json

import pytest

from usr.plugins.jcode_harness.helpers.daemon import NoCredentialsError
from usr.plugins.jcode_harness.tools.jcode_skill import JcodeSkill
from usr.plugins.jcode_harness.tests.unit.conftest import make_tool, read_line


pytestmark = pytest.mark.asyncio


async def test_skill_list_returns_output(
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
            b'{"type":"tool_done","id":"t1","name":"skill_manage",'
            b'"output":"skill-a\\nskill-b"}\n'
        )
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeSkill, fake_agent)
    resp = await tool.execute(action="list", working_dir="/tmp")
    assert "skill-a" in resp.message
    assert "skill-b" in resp.message
    assert "action=list" in payloads[0]


async def test_skill_load_with_name(
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
            b'{"type":"tool_done","id":"t1","name":"skill_manage",'
            b'"output":"loaded"}\n'
        )
        writer.write(
            b'{"type":"done","id":' + str(msg_id).encode() + b"}\n"
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeSkill, fake_agent)
    resp = await tool.execute(
        action="load",
        name="my-skill",
        working_dir="/tmp",
    )
    assert resp.message == "loaded"
    assert "action=load" in payloads[0]
    assert "my-skill" in payloads[0]


async def test_skill_invalid_action(fake_agent):
    tool = make_tool(JcodeSkill, fake_agent)
    resp = await tool.execute(action="explode", working_dir="/tmp")
    assert "invalid action" in resp.message
    assert "explode" in resp.message
    assert resp.break_loop is False


async def test_skill_no_binary(fake_agent, patch_supervisor):
    patch_supervisor(None, binary=None)
    tool = make_tool(JcodeSkill, fake_agent)
    resp = await tool.execute(action="list", working_dir="/tmp")
    assert "not installed" in resp.message


async def test_skill_no_creds(fake_agent, patch_supervisor):
    patch_supervisor(None, raises=NoCredentialsError("no providers"))
    tool = make_tool(JcodeSkill, fake_agent)
    resp = await tool.execute(action="list", working_dir="/tmp")
    assert "no providers" in resp.message
