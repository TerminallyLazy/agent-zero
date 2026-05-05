"""Unit tests for the persistent client_instance_id store."""

from __future__ import annotations

import stat
import uuid
from pathlib import Path

import pytest

from usr.plugins.jcode_harness.helpers import persistence as persistence_mod
from usr.plugins.jcode_harness.helpers.persistence import (
    get_or_create_client_instance_id,
)


@pytest.fixture
def patched_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Redirect client_instance_persist_path to a tmp directory."""
    sessions = tmp_path / "sessions"
    sessions.mkdir(mode=0o700)

    def fake_path(a0_ctx_id: str, instance_id: str | None = None) -> Path:
        return sessions / f"{a0_ctx_id}.json"

    monkeypatch.setattr(
        persistence_mod, "client_instance_persist_path", fake_path
    )
    return sessions


def test_persist_and_load_stable(patched_persist: Path) -> None:
    a = get_or_create_client_instance_id("ctx-1")
    b = get_or_create_client_instance_id("ctx-1")
    assert a == b


def test_distinct_ctx_ids_get_distinct_uuids(patched_persist: Path) -> None:
    a = get_or_create_client_instance_id("ctx-A")
    b = get_or_create_client_instance_id("ctx-B")
    assert a != b


def test_corrupted_json_recovered(
    patched_persist: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = patched_persist / "ctx-corrupt.json"
    target.write_text("{not valid json")

    cid = get_or_create_client_instance_id("ctx-corrupt")

    # Returns a valid UUID4 string.
    parsed = uuid.UUID(cid)
    assert parsed.version == 4

    # File now contains valid JSON with that id.
    import json as _json

    assert _json.loads(target.read_text()) == {"client_instance_id": cid}

    # Corruption was logged to stderr.
    captured = capsys.readouterr()
    assert "corrupt" in captured.err.lower()


def test_missing_key_recovered(patched_persist: Path) -> None:
    target = patched_persist / "ctx-nokey.json"
    target.write_text('{"other_field": "x"}')

    cid = get_or_create_client_instance_id("ctx-nokey")
    assert uuid.UUID(cid).version == 4


def test_file_perms_0600(patched_persist: Path) -> None:
    get_or_create_client_instance_id("ctx-perm")
    f = patched_persist / "ctx-perm.json"
    mode = stat.S_IMODE(f.stat().st_mode)
    assert mode == 0o600, oct(mode)


def test_uuid_format(patched_persist: Path) -> None:
    cid = get_or_create_client_instance_id("ctx-uuid")
    parsed = uuid.UUID(cid, version=4)
    assert str(parsed) == cid
