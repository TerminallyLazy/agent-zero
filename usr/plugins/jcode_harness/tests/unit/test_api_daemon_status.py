"""Tests for usr.plugins.jcode_harness.api.daemon_status."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


def _make_handler():
    from usr.plugins.jcode_harness.api.daemon_status import DaemonStatus

    return DaemonStatus(app=MagicMock(), thread_lock=MagicMock())


def test_get_methods_includes_get_and_post():
    from usr.plugins.jcode_harness.api.daemon_status import DaemonStatus

    assert DaemonStatus.get_methods() == ["GET", "POST"]


def test_returns_error_when_binary_missing(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: None)
    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out == {"running": False, "error": "binary not installed"}


def test_returns_health_dict_when_binary_present(monkeypatch, tmp_path):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod
    from usr.plugins.jcode_harness.helpers import paths as paths_mod

    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode")
    monkeypatch.setattr(paths_mod, "jcode_runtime_dir", lambda: tmp_path)

    fake_health = {
        "running": True,
        "pid": 1234,
        "socket": str(tmp_path / "j.sock"),
        "log_files": [],
        "started_at": 1234567.0,
    }
    monkeypatch.setattr(
        daemon_mod.DaemonSupervisor, "health", lambda self: dict(fake_health)
    )

    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out == fake_health
    # Spot-check the keys a UI panel would render.
    assert "running" in out
    assert "pid" in out
    assert "socket" in out
