"""Tests for the agent_init/jcode_register extension.

Critical contract: execute() must be SYNC. A0 calls this hook via
helpers.extension.call_extensions_sync, which raises ValueError if execute
returns an awaitable. Regression caught 2026-05-05 from a live A0 chat-create
500 error.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from usr.plugins.jcode_harness.extensions.python.agent_init.jcode_register import (
    JcodeRegister,
)


def test_execute_is_sync_not_async():
    """A0's call_extensions_sync rejects coroutine-returning extensions.
    JcodeRegister.execute MUST be a regular function, not async def."""
    assert not inspect.iscoroutinefunction(JcodeRegister.execute), (
        "execute() must be sync — A0 calls agent_init via "
        "call_extensions_sync which raises ValueError on awaitables"
    )


def test_execute_returns_none_not_awaitable():
    """Concrete check: calling execute() returns None directly, not a coroutine."""
    ext = JcodeRegister(agent=None)
    result = ext.execute()
    assert result is None
    assert not isinstance(result, Awaitable)


def test_no_op_when_agent_is_none():
    ext = JcodeRegister(agent=None)
    assert ext.execute() is None


def test_no_op_when_profile_not_jcode_coder(monkeypatch):
    """Different profile => DaemonSupervisor never instantiated."""
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    sup_factory = MagicMock(side_effect=AssertionError("should not construct"))
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", sup_factory)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode")

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="default")
    ext = JcodeRegister(agent=agent)
    assert ext.execute() is None
    sup_factory.assert_not_called()


def test_no_op_when_binary_missing(monkeypatch):
    """profile=jcode_coder but no binary => no spawn."""
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    sup_factory = MagicMock(side_effect=AssertionError("should not construct"))
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", sup_factory)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: None)

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="jcode_coder")
    ext = JcodeRegister(agent=agent)
    assert ext.execute() is None
    sup_factory.assert_not_called()


def test_no_op_when_daemon_already_running(monkeypatch):
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
    assert ext.execute() is None
    fake_sup.is_running.assert_called_once()


def test_no_op_outside_event_loop(monkeypatch):
    """Called from a sync context with no running loop => silent no-op
    (asyncio.get_running_loop() raises RuntimeError; extension swallows it).
    A0's agent_init runs sync via call_extensions_sync, which may or may not
    have a loop attached; we must not crash either way."""
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    fake_sup = MagicMock()
    fake_sup.is_running.return_value = False
    fake_sup.ensure_running = MagicMock(
        side_effect=AssertionError("must not be invoked"),
    )
    monkeypatch.setattr(daemon_mod, "DaemonSupervisor", lambda *a, **kw: fake_sup)
    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode")

    agent = MagicMock()
    agent.config = SimpleNamespace(profile="jcode_coder")
    ext = JcodeRegister(agent=agent)
    # No event loop: must not raise
    assert ext.execute() is None


@pytest.mark.asyncio
async def test_fires_warmup_when_profile_matches_and_loop_is_running(monkeypatch):
    """Profile match + daemon idle + running loop => fire-and-forget ensure_running."""
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
    assert ext.execute() is None  # SYNC — no await

    # The warmup runs in a background task; allow the loop to schedule it.
    try:
        await asyncio.wait_for(awaited.wait(), timeout=1.0)
    except asyncio.TimeoutError:
        pytest.fail("ensure_running was not awaited from background task")
