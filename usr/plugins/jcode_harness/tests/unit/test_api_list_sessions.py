"""Tests for usr.plugins.jcode_harness.api.list_sessions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_handler():
    from usr.plugins.jcode_harness.api.list_sessions import ListSessions

    return ListSessions(app=MagicMock(), thread_lock=MagicMock())


def _write_session(base: Path, sid: str, payload: dict) -> None:
    d = base / sid
    d.mkdir(parents=True)
    (d / "session.json").write_text(json.dumps(payload))


def test_get_methods_includes_get_and_post():
    from usr.plugins.jcode_harness.api.list_sessions import ListSessions

    assert ListSessions.get_methods() == ["GET", "POST"]


def test_returns_empty_when_sessions_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out == {"sessions": []}


def test_returns_sorted_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    base = tmp_path / ".jcode" / "sessions"
    base.mkdir(parents=True)
    _write_session(
        base,
        "sess_old",
        {
            "title": "old",
            "updated_at": 100,
            "working_dir": "/tmp",
            "model": "m1",
        },
    )
    _write_session(
        base,
        "sess_new",
        {
            "title": "new",
            "updated_at": 300,
            "working_dir": "/tmp",
            "model": "m2",
        },
    )
    _write_session(
        base,
        "sess_mid",
        {"title": "mid", "updated_at": 200, "working_dir": "/tmp"},
    )

    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    ids = [s["id"] for s in out["sessions"]]
    assert ids == ["sess_new", "sess_mid", "sess_old"]
    assert out["sessions"][0]["title"] == "new"
    assert out["sessions"][0]["model"] == "m2"


def test_skips_corrupt_session_json(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    base = tmp_path / ".jcode" / "sessions"
    base.mkdir(parents=True)
    _write_session(base, "sess_good", {"title": "ok", "updated_at": 1})
    bad = base / "sess_bad"
    bad.mkdir()
    (bad / "session.json").write_text("not-json{{{")

    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    ids = [s["id"] for s in out["sessions"]]
    assert ids == ["sess_good"]


def test_skips_non_dir_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    base = tmp_path / ".jcode" / "sessions"
    base.mkdir(parents=True)
    _write_session(base, "sess_a", {"title": "a", "updated_at": 1})
    # Stray file at the journal root — must be ignored.
    (base / "stray.txt").write_text("hello")

    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert [s["id"] for s in out["sessions"]] == ["sess_a"]


def test_includes_provider_session_id_when_present(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    base = tmp_path / ".jcode" / "sessions"
    base.mkdir(parents=True)
    _write_session(
        base,
        "sess_x",
        {
            "title": "x",
            "updated_at": 1,
            "provider_session_id": "psid-123",
            "provider_key": "claude",
        },
    )

    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out["sessions"][0]["provider_session_id"] == "psid-123"
    assert out["sessions"][0]["provider_key"] == "claude"


def test_skips_dir_without_session_json(monkeypatch, tmp_path):
    """A session dir with no session.json must be ignored cleanly."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    base = tmp_path / ".jcode" / "sessions"
    base.mkdir(parents=True)
    (base / "incomplete").mkdir()
    _write_session(base, "ok", {"title": "ok", "updated_at": 1})

    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert [s["id"] for s in out["sessions"]] == ["ok"]
