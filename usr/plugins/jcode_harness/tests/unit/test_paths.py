"""Unit tests for the per-instance path resolver."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from usr.plugins.jcode_harness.helpers import paths as paths_mod
from usr.plugins.jcode_harness.helpers.paths import (
    client_instance_persist_path,
    jcode_runtime_dir,
    overlay_config_path,
    pid_path,
    socket_path,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` to a tmp directory so tests never touch ~/.

    Also forces the non-Windows code path (the test suite runs on darwin/linux
    in CI; Windows users get a separate code path that is exercised by
    inspection).
    """
    monkeypatch.setattr(paths_mod.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(paths_mod.platform, "system", lambda: "Darwin")
    return tmp_path


def _mode_bits(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def test_jcode_runtime_dir_under_amplihack(fake_home: Path) -> None:
    d = jcode_runtime_dir("abc123")
    assert d == fake_home / ".amplihack" / "jcode" / "abc123"
    assert d.is_dir()


def test_jcode_runtime_dir_creates_with_0700(fake_home: Path) -> None:
    d = jcode_runtime_dir("freshid")
    assert d.is_dir()
    assert _mode_bits(d) == 0o700, oct(_mode_bits(d))


def test_jcode_runtime_dir_chmods_existing(fake_home: Path) -> None:
    target = fake_home / ".amplihack" / "jcode" / "preexists"
    target.mkdir(parents=True)
    target.chmod(0o755)
    assert _mode_bits(target) == 0o755

    d = jcode_runtime_dir("preexists")
    assert d == target
    assert _mode_bits(d) == 0o700, (
        f"expected 0o700 after call, got {oct(_mode_bits(d))}"
    )


def test_socket_path_under_runtime_dir(fake_home: Path) -> None:
    s = socket_path("iid1")
    assert s == jcode_runtime_dir("iid1") / "jcode.sock"
    # parent must exist (runtime dir was created)
    assert s.parent.is_dir()


def test_pid_path_under_runtime_dir(fake_home: Path) -> None:
    p = pid_path("iid1")
    assert p == jcode_runtime_dir("iid1") / "pid"


def test_client_instance_persist_path_creates_sessions_subdir(
    fake_home: Path,
) -> None:
    p = client_instance_persist_path("ctx-42", "iidX")
    assert p.name == "ctx-42.json"
    assert p.parent.name == "sessions"
    assert p.parent.is_dir()
    assert _mode_bits(p.parent) == 0o700, oct(_mode_bits(p.parent))


def test_overlay_config_path(fake_home: Path) -> None:
    cfg = overlay_config_path("iid1")
    assert cfg == jcode_runtime_dir("iid1") / "jcode-config.toml"


def test_default_instance_id_used_when_omitted(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When instance_id is None, resolver delegates to compute_instance_id()."""
    monkeypatch.setattr(
        paths_mod, "compute_instance_id", lambda: "deadbeefcafe"
    )
    d = jcode_runtime_dir()
    assert d.name == "deadbeefcafe"
