"""Tests for the agent_init/jcode_register extension."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from usr.plugins.jcode_harness.extensions.python.agent_init.jcode_register import (
    JcodeRegister,
)


@pytest.mark.asyncio
async def test_no_op_when_agent_is_none():
    ext = JcodeRegister(agent=None)
    # Must not raise.
    assert await ext.execute() is None


@pytest.mark.asyncio
async def test_no_op_when_profile_not_jcode_coder(monkeypatch):
    """Different profile => DaemonSupervisor never instantiated."""
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    sup_factory = MagicMock(side_effect=AssertionError("should not construct"))
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", sup_factory)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode")

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="default")
    ext = JcodeRegister(agent=agent)
    assert await ext.execute() is None
    sup_factory.assert_not_called()


@pytest.mark.asyncio
async def test_no_op_when_binary_missing(monkeypatch):
    """profile=jcode_coder but no binary => no spawn."""
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    sup_factory = MagicMock(side_effect=AssertionError("should not construct"))
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", sup_factory)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: None)

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="jcode_coder")
    ext = JcodeRegister(agent=agent)
    assert await ext.execute() is None
    sup_factory.assert_not_called()


@pytest.mark.asyncio
async def test_no_op_when_daemon_already_running(monkeypatch):
    """is_running True => ensure_running not called."""
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
    ext = JcodeRegister(agent=agent)
    assert await ext.execute() is None
    fake_sup.is_running.assert_called_once()


@pytest.mark.asyncio
async def test_fires_warmup_when_profile_matches_and_daemon_idle(monkeypatch):
    """Profile match + daemon idle => fire-and-forget ensure_running."""
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    fake_sup = MagicMock()
    fake_sup.is_running.return_value = False

    awaited = asyncio.Event()

    async def _ensure(working_dir):
        awaited.set()
        return "/tmp/sock"

    fake_sup.ensure_running = _ensure
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", lambda *a, **kw: fake_sup)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode")

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="jcode_coder")
    ext = JcodeRegister(agent=agent)
    assert await ext.execute() is None

    # The warmup runs in a background task; allow the loop to schedule it.
    try:
        await asyncio.wait_for(awaited.wait(), timeout=1.0)
    except asyncio.TimeoutError:
        pytest.fail("ensure_running was not awaited from background task")
