"""Unit tests for :class:`JcodeResume`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from usr.plugins.jcode_harness.helpers.daemon import NoCredentialsError
from usr.plugins.jcode_harness.tools.jcode_resume import JcodeResume
from usr.plugins.jcode_harness.tests.unit.conftest import make_tool, read_line


pytestmark = pytest.mark.asyncio


def _seed_session(base: Path, sid: str, title: str = "", provider: str = "jcode",
                  updated_at: int = 0) -> None:
    d = base / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "session.json").write_text(
        json.dumps(
            {
                "title": title,
                "provider_key": provider,
                "working_dir": "/wd",
                "updated_at": updated_at,
            }
        )
    )


async def test_list_sessions_empty(fake_agent, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    tool = make_tool(JcodeResume, fake_agent)
    resp = await tool.execute()
    assert "no resumable sessions" in resp.message


async def test_list_sessions_returns_recent_first(
    fake_agent, tmp_path, monkeypatch
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    base = tmp_path / ".jcode" / "sessions"
    _seed_session(base, "old", title="O", updated_at=10)
    _seed_session(base, "mid", title="M", updated_at=20)
    _seed_session(base, "new", title="N", updated_at=30)

    tool = make_tool(JcodeResume, fake_agent)
    resp = await tool.execute()
    lines = resp.message.splitlines()
    ids = [ln.split()[0] for ln in lines]
    assert ids == ["new", "mid", "old"]


async def test_list_sessions_skips_corrupt_session_json(
    fake_agent, tmp_path, monkeypatch
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    base = tmp_path / ".jcode" / "sessions"
    _seed_session(base, "ok", title="ok", updated_at=5)
    bad = base / "bad"
    bad.mkdir(parents=True)
    (bad / "session.json").write_text("{not valid json")

    tool = make_tool(JcodeResume, fake_agent)
    resp = await tool.execute()
    lines = resp.message.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("ok ")


async def test_list_sessions_caps_at_20(fake_agent, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    base = tmp_path / ".jcode" / "sessions"
    for i in range(25):
        _seed_session(base, f"s{i:02d}", title=f"t{i}", updated_at=i)
    tool = make_tool(JcodeResume, fake_agent)
    resp = await tool.execute()
    assert len(resp.message.splitlines()) == 20


async def test_resume_returns_history_summary(
    fake_agent, fake_daemon, patch_supervisor
):
    async def script(daemon, reader, writer):
        # subscribe
        await read_line(reader)
        writer.write(b'{"type":"session","session_id":"x"}\n')
        await writer.drain()
        # get_history
        await read_line(reader)
        writer.write(
            b'{"type":"history","id":1,"session_id":"x",'
            b'"messages":[{"r":"u"},{"r":"a"},{"r":"u"}]}\n'
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    patch_supervisor(sock)

    tool = make_tool(JcodeResume, fake_agent)
    resp = await tool.execute(session_id="x", working_dir="/tmp")
    assert resp.message == "Resumed session x: 3 prior messages"


async def test_resume_no_binary_returns_friendly_message(
    fake_agent, patch_supervisor
):
    patch_supervisor(None, binary=None)
    tool = make_tool(JcodeResume, fake_agent)
    resp = await tool.execute(session_id="x", working_dir="/tmp")
    assert "not installed" in resp.message


async def test_resume_no_creds_returns_friendly_message(
    fake_agent, patch_supervisor
):
    patch_supervisor(None, raises=NoCredentialsError("no providers"))
    tool = make_tool(JcodeResume, fake_agent)
    resp = await tool.execute(session_id="x", working_dir="/tmp")
    assert "no providers" in resp.message
