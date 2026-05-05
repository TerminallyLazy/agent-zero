"""Tests for the monologue_start/jcode_warmup extension."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from usr.plugins.jcode_harness.extensions.python.monologue_start.jcode_warmup import (
    JcodeWarmup,
)


@pytest.mark.asyncio
async def test_no_op_when_agent_is_none():
    ext = JcodeWarmup(agent=None)
    assert await ext.execute() is None


@pytest.mark.asyncio
async def test_no_op_when_profile_not_jcode_coder(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    sup_factory = MagicMock(side_effect=AssertionError("should not construct"))
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", sup_factory)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode")

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="default")
    ext = JcodeWarmup(agent=agent)
    assert await ext.execute() is None
    sup_factory.assert_not_called()


@pytest.mark.asyncio
async def test_no_op_when_binary_missing(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    sup_factory = MagicMock(side_effect=AssertionError("should not construct"))
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", sup_factory)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: None)

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="jcode_coder")
    ext = JcodeWarmup(agent=agent)
    assert await ext.execute() is None
    sup_factory.assert_not_called()


@pytest.mark.asyncio
async def test_no_op_when_daemon_already_running(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    fake_sup = MagicMock()
    fake_sup.is_running.return_value = True

    async def _ensure(*a, **kw):
        raise AssertionError("ensure_running must not be called")

    fake_sup.ensure_running = _ensure
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", lambda *a, **kw: fake_sup)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode")

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="jcode_coder")
    ext = JcodeWarmup(agent=agent)
    assert await ext.execute() is None
    fake_sup.is_running.assert_called_once()


@pytest.mark.asyncio
async def test_warms_when_profile_matches_and_daemon_idle(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    fake_sup = MagicMock()
    fake_sup.is_running.return_value = False

    awaited_with: dict = {}

    async def _ensure(working_dir):
        awaited_with["wd"] = working_dir
        return "/tmp/sock"

    fake_sup.ensure_running = _ensure
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", lambda *a, **kw: fake_sup)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode")

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="jcode_coder")
    ext = JcodeWarmup(agent=agent)
    assert await ext.execute(loop_data=object()) is None
    assert "wd" in awaited_with  # ensure_running was awaited inline


@pytest.mark.asyncio
async def test_silently_swallows_no_credentials_error(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    fake_sup = MagicMock()
    fake_sup.is_running.return_value = False

    async def _ensure(working_dir):
        raise daemon_mod.NoCredentialsError("no creds wired")

    fake_sup.ensure_running = _ensure
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", lambda *a, **kw: fake_sup)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode")

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="jcode_coder")
    ext = JcodeWarmup(agent=agent)
    # Must not raise.
    assert await ext.execute() is None
