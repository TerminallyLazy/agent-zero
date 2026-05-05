"""Tests for usr.plugins.jcode_harness.api.login_provider."""

from __future__ import annotations

import asyncio
import json
import subprocess
from unittest.mock import MagicMock

import pytest


def _make_handler():
    from usr.plugins.jcode_harness.api.login_provider import LoginProvider

    return LoginProvider(app=MagicMock(), thread_lock=MagicMock())


def _patch_binary(monkeypatch, path: str | None):
    import usr.plugins.jcode_harness.api.login_provider as mod

    monkeypatch.setattr(mod, "locate_jcode_binary", lambda: path)


def test_missing_provider_returns_error():
    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out == {"ok": False, "error": "provider required"}


def test_no_binary_returns_error(monkeypatch):
    _patch_binary(monkeypatch, None)
    h = _make_handler()
    out = asyncio.run(h.process({"provider": "claude"}, MagicMock()))
    assert out == {"ok": False, "error": "jcode not installed"}


def test_returns_auth_url_on_success(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")
    captured = {}

    def fake_check_output(cmd, **kw):
        captured["cmd"] = cmd
        return json.dumps({"auth_url": "https://oauth/x"})

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(h.process({"provider": "openai"}, MagicMock()))
    assert out == {"ok": True, "auth_url": "https://oauth/x", "user_code": None}
    # Spike 0.8 flag set verified.
    cmd = captured["cmd"]
    assert "--print-auth-url" in cmd
    assert "--json" in cmd
    assert "--no-browser" in cmd
    assert "--provider" in cmd
    assert "openai" in cmd


def test_returns_user_code_when_present(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")

    def fake_check_output(cmd, **kw):
        return json.dumps(
            {"auth_url": "https://oauth/x", "user_code": "AB12-CD34"}
        )

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(h.process({"provider": "claude"}, MagicMock()))
    assert out["ok"] is True
    assert out["user_code"] == "AB12-CD34"


def test_calledprocesserror_returns_friendly_error(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")

    def fake_check_output(cmd, **kw):
        raise subprocess.CalledProcessError(
            returncode=1, cmd=cmd, output="provider unknown: foo"
        )

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(h.process({"provider": "foo"}, MagicMock()))
    assert out["ok"] is False
    assert "provider unknown" in out["error"]


def test_calledprocesserror_truncates_long_output(monkeypatch):
    """Stderr blobs > 500 chars get clamped so we don't bloat responses."""
    _patch_binary(monkeypatch, "/fake/jcode")
    long = "x" * 5000

    def fake_check_output(cmd, **kw):
        raise subprocess.CalledProcessError(
            returncode=2, cmd=cmd, output=long
        )

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(h.process({"provider": "claude"}, MagicMock()))
    assert out["ok"] is False
    assert len(out["error"]) <= 500


def test_timeout_returns_error(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")

    def fake_check_output(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(h.process({"provider": "claude"}, MagicMock()))
    assert out == {"ok": False, "error": "login timed out"}


def test_invalid_json_output_returns_error(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")

    def fake_check_output(cmd, **kw):
        return "not-json{{{"

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(h.process({"provider": "claude"}, MagicMock()))
    assert out["ok"] is False
    assert "error" in out
