"""Unit tests for :class:`JcodeSelfDev`."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from helpers.tool import Response
from usr.plugins.jcode_harness.tools.jcode_self_dev import JcodeSelfDev
from usr.plugins.jcode_harness.tests.unit.conftest import make_tool


pytestmark = pytest.mark.asyncio


async def test_selfdev_no_cargo_returns_rustup_message(fake_agent, monkeypatch):
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.tools.jcode_self_dev.shutil.which",
        lambda _: None,
    )
    tool = make_tool(JcodeSelfDev, fake_agent)
    resp = await tool.execute(task="bump version")
    assert "rustup.rs" in resp.message
    assert "Rust toolchain" in resp.message


async def test_selfdev_empty_task_returns_error(fake_agent, monkeypatch):
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.tools.jcode_self_dev.shutil.which",
        lambda _: "/usr/bin/cargo",
    )
    tool = make_tool(JcodeSelfDev, fake_agent)
    resp = await tool.execute(task="   ")
    assert "task description required" in resp.message


async def test_selfdev_with_cargo_delegates_to_session(
    fake_agent, monkeypatch
):
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.tools.jcode_self_dev.shutil.which",
        lambda _: "/usr/bin/cargo",
    )

    captured: dict[str, object] = {}

    async def _fake_execute(self, **kwargs):
        captured.update(kwargs)
        return Response(message="ok", break_loop=False)

    with patch(
        "usr.plugins.jcode_harness.tools.jcode_self_dev.JcodeSession.execute",
        new=_fake_execute,
    ):
        tool = make_tool(JcodeSelfDev, fake_agent)
        resp = await tool.execute(task="rename foo to bar")

    assert resp.message == "ok"
    assert "task" in captured
    assert captured["task"].startswith("Enter selfdev mode and: ")
    assert "rename foo to bar" in captured["task"]
