"""Tests for usr.plugins.jcode_harness.api.purge_imported_profiles."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


def _make_handler():
    from usr.plugins.jcode_harness.api.purge_imported_profiles import (
        PurgeImported,
    )

    return PurgeImported(app=MagicMock(), thread_lock=MagicMock())


def test_returns_error_when_binary_missing(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: None)
    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out == {
        "ok": False,
        "error": "jcode not installed",
        "purged": [],
    }


def test_returns_purged_list_on_success(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod
    from usr.plugins.jcode_harness.helpers import (
        provider_import as pi_mod,
    )

    monkeypatch.setattr(
        daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode"
    )
    monkeypatch.setattr(
        pi_mod,
        "purge_imported_profiles",
        lambda bin_path: ["_a0_imported_x", "_a0_imported_y"],
    )
    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out == {
        "ok": True,
        "purged": ["_a0_imported_x", "_a0_imported_y"],
    }


def test_returns_empty_list_when_nothing_to_purge(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod
    from usr.plugins.jcode_harness.helpers import (
        provider_import as pi_mod,
    )

    monkeypatch.setattr(
        daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode"
    )
    monkeypatch.setattr(pi_mod, "purge_imported_profiles", lambda b: [])
    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out == {"ok": True, "purged": []}


def test_returns_error_when_purge_raises(monkeypatch):
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod
    from usr.plugins.jcode_harness.helpers import (
        provider_import as pi_mod,
    )

    monkeypatch.setattr(
        daemon_mod, "locate_jcode_binary", lambda: "/fake/jcode"
    )

    def boom(_):
        raise RuntimeError("config.toml unreadable")

    monkeypatch.setattr(pi_mod, "purge_imported_profiles", boom)
    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out["ok"] is False
    assert "config.toml unreadable" in out["error"]
    assert out["purged"] == []
