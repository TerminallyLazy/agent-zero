"""Tests for usr.plugins.jcode_harness.api.complete_login."""

from __future__ import annotations

import asyncio
import json
import subprocess
from unittest.mock import MagicMock

import pytest


def _make_handler():
    from usr.plugins.jcode_harness.api.complete_login import CompleteLogin

    return CompleteLogin(app=MagicMock(), thread_lock=MagicMock())


def _patch_binary(monkeypatch, path: str | None):
    import usr.plugins.jcode_harness.api.complete_login as mod

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


def test_callback_url_path(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")
    captured = {}

    def fake_check_output(cmd, **kw):
        captured["cmd"] = cmd
        return json.dumps({"status": "complete"})

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(
        h.process(
            {
                "provider": "claude",
                "callback_url": "https://localhost:1234/cb?code=abc",
            },
            MagicMock(),
        )
    )
    assert out["ok"] is True
    cmd = captured["cmd"]
    assert "--callback-url" in cmd
    assert "https://localhost:1234/cb?code=abc" in cmd
    assert "--auth-code" not in cmd
    assert "--complete" not in cmd


def test_auth_code_path(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")
    captured = {}

    def fake_check_output(cmd, **kw):
        captured["cmd"] = cmd
        return json.dumps({"status": "ok"})

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(
        h.process(
            {"provider": "openai", "auth_code": "device-code-xyz"},
            MagicMock(),
        )
    )
    assert out["ok"] is True
    cmd = captured["cmd"]
    assert "--auth-code" in cmd
    assert "device-code-xyz" in cmd
    assert "--callback-url" not in cmd
    assert "--complete" not in cmd


def test_complete_path_when_neither_supplied(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")
    captured = {}

    def fake_check_output(cmd, **kw):
        captured["cmd"] = cmd
        return ""

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(h.process({"provider": "claude"}, MagicMock()))
    assert out == {"ok": True, "stdout": ""}
    cmd = captured["cmd"]
    assert "--complete" in cmd
    assert "--callback-url" not in cmd
    assert "--auth-code" not in cmd


def test_callback_takes_priority_over_auth_code(monkeypatch):
    """Both supplied -> callback wins (handler if/elif order)."""
    _patch_binary(monkeypatch, "/fake/jcode")
    captured = {}

    def fake_check_output(cmd, **kw):
        captured["cmd"] = cmd
        return json.dumps({})

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(
        h.process(
            {
                "provider": "claude",
                "callback_url": "https://x/cb",
                "auth_code": "should-not-be-used",
            },
            MagicMock(),
        )
    )
    assert out["ok"] is True
    cmd = captured["cmd"]
    assert "--callback-url" in cmd
    assert "--auth-code" not in cmd


def test_calledprocesserror_returns_friendly_error(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")

    def fake_check_output(cmd, **kw):
        raise subprocess.CalledProcessError(
            returncode=1, cmd=cmd, output="auth failed: bad code"
        )

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(
        h.process(
            {"provider": "claude", "auth_code": "x"}, MagicMock()
        )
    )
    assert out["ok"] is False
    assert "auth failed" in out["error"]


def test_timeout_returns_error(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")

    def fake_check_output(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(h.process({"provider": "claude"}, MagicMock()))
    assert out == {"ok": False, "error": "login timed out"}


def test_non_json_stdout_returned_verbatim(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")

    def fake_check_output(cmd, **kw):
        return "Login complete.\n"

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(
        h.process(
            {"provider": "claude", "callback_url": "https://x/cb"},
            MagicMock(),
        )
    )
    assert out == {"ok": True, "stdout": "Login complete."}


def test_json_stdout_merged_into_response(monkeypatch):
    _patch_binary(monkeypatch, "/fake/jcode")

    def fake_check_output(cmd, **kw):
        return json.dumps({"status": "complete", "user": "alice"})

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    h = _make_handler()
    out = asyncio.run(
        h.process(
            {"provider": "claude", "auth_code": "y"}, MagicMock()
        )
    )
    assert out["ok"] is True
    assert out["status"] == "complete"
    assert out["user"] == "alice"
