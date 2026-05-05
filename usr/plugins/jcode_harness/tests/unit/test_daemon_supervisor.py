"""Tests for usr.plugins.jcode_harness.helpers.daemon."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from usr.plugins.jcode_harness.helpers import daemon as daemon_mod
from usr.plugins.jcode_harness.helpers.daemon import (
    DaemonSupervisor,
    NoCredentialsError,
    locate_jcode_binary,
)


# ---------------------------------------------------------------------------
# Fake jcode daemon — minimal Python script that binds the requested socket
# with mode 0o600 and sleeps. Used in place of the real jcode binary.
# ---------------------------------------------------------------------------

_FAKE_DAEMON_SCRIPT = r"""
import os, socket, sys, time, signal
def parse_socket():
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--socket" and i + 1 < len(args):
            return args[i + 1]
    return None
sock_path = parse_socket()
if sock_path is None:
    sys.exit(2)
try:
    os.unlink(sock_path)
except FileNotFoundError:
    pass
s = socket.socket(socket.AF_UNIX)
s.bind(sock_path)
os.chmod(sock_path, 0o600)
s.listen(1)
# Sleep until killed; respond to SIGTERM cleanly.
def _bye(*_): sys.exit(0)
signal.signal(signal.SIGTERM, _bye)
time.sleep(60)
"""


@pytest.fixture
def fake_jcode_binary(tmp_path: Path) -> str:
    """Write a tiny shell wrapper that execs Python with the fake script."""
    script_py = tmp_path / "fake_daemon.py"
    script_py.write_text(_FAKE_DAEMON_SCRIPT)
    wrapper = tmp_path / "fake_jcode"
    # We do not honor the `serve` subcommand — fake just runs the script.
    wrapper.write_text(
        "#!/bin/sh\nexec "
        + sys.executable
        + " "
        + str(script_py)
        + ' "$@"\n'
    )
    wrapper.chmod(0o755)
    return str(wrapper)


@pytest.fixture
def short_inst() -> Path:
    """Short instance_dir for AF_UNIX (104-char path limit on macOS).

    pytest's tmp_path nests deeply enough that the resulting socket path
    overflows. Use /tmp directly with a short prefix.
    """
    d = Path(tempfile.mkdtemp(prefix="jch-", dir="/tmp"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# locate_jcode_binary
# ---------------------------------------------------------------------------


def test_locate_binary_path_first(monkeypatch):
    monkeypatch.setattr(daemon_mod.shutil, "which", lambda _: "/usr/bin/jcode")
    assert locate_jcode_binary() == "/usr/bin/jcode"


def test_locate_binary_falls_back_to_amplihack(monkeypatch, tmp_path):
    monkeypatch.setattr(daemon_mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    stable = tmp_path / ".jcode" / "builds" / "stable" / "jcode"
    stable.parent.mkdir(parents=True)
    stable.write_text("#!/bin/sh\nexit 0\n")
    stable.chmod(0o755)
    assert locate_jcode_binary() == str(stable)


def test_locate_binary_returns_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(daemon_mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert locate_jcode_binary() is None


def test_locate_binary_skips_non_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(daemon_mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    stable = tmp_path / ".jcode" / "builds" / "stable" / "jcode"
    stable.parent.mkdir(parents=True)
    stable.write_text("not exec\n")
    stable.chmod(0o644)
    assert locate_jcode_binary() is None


# ---------------------------------------------------------------------------
# is_running predicates
# ---------------------------------------------------------------------------


def test_is_running_false_when_no_pid_file(tmp_path):
    sup = DaemonSupervisor("/bin/true", tmp_path)
    assert sup.is_running() is False


def test_is_running_false_when_socket_missing(tmp_path):
    sup = DaemonSupervisor("/bin/true", tmp_path)
    sup.pid_file.write_text(str(os.getpid()))
    assert sup.is_running() is False


def test_is_running_false_when_pid_dead(tmp_path):
    sup = DaemonSupervisor("/bin/true", tmp_path)
    # Put a definitely-not-our-process PID and create a dummy socket file.
    sup.pid_file.write_text("999999")
    sup.socket_file.touch(mode=0o600)
    assert sup.is_running() is False


# ---------------------------------------------------------------------------
# _has_creds
# ---------------------------------------------------------------------------


def test_has_creds_via_env(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    sup = DaemonSupervisor("/bin/true", tmp_path / "inst")
    assert sup._has_creds() is True


def test_has_creds_via_auth_file(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    for key in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    auth = tmp_path / ".jcode" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text("{}")
    sup = DaemonSupervisor("/bin/true", tmp_path / "inst")
    assert sup._has_creds() is True


def test_has_creds_false_when_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    for key in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    # And make `provider list --json` blow up.
    def fake_run(*a, **kw):
        raise FileNotFoundError("no jcode binary")
    monkeypatch.setattr(daemon_mod.subprocess, "run", fake_run)
    sup = DaemonSupervisor("/nonexistent", tmp_path / "inst")
    assert sup._has_creds() is False


# ---------------------------------------------------------------------------
# ensure_running paths
# ---------------------------------------------------------------------------


def test_ensure_running_raises_no_credentials(monkeypatch, tmp_path):
    sup = DaemonSupervisor("/bin/true", tmp_path / "inst")
    monkeypatch.setattr(sup, "_has_creds", lambda: False)
    with pytest.raises(NoCredentialsError):
        asyncio.run(sup.ensure_running(str(tmp_path)))


def test_ensure_running_spawns_and_writes_pidfile(
    monkeypatch, tmp_path, short_inst, fake_jcode_binary
):
    sup = DaemonSupervisor(fake_jcode_binary, short_inst)
    monkeypatch.setattr(sup, "_has_creds", lambda: True)
    try:
        socket_path = asyncio.run(sup.ensure_running(str(tmp_path)))
        assert Path(socket_path) == sup.socket_file
        assert sup.socket_file.exists()
        assert sup.pid_file.exists()
        pid = int(sup.pid_file.read_text())
        # Child is alive
        os.kill(pid, 0)
    finally:
        sup.stop()


def test_overlay_config_written_with_gateway_disabled(
    monkeypatch, tmp_path, short_inst, fake_jcode_binary
):
    sup = DaemonSupervisor(fake_jcode_binary, short_inst)
    monkeypatch.setattr(sup, "_has_creds", lambda: True)
    try:
        asyncio.run(sup.ensure_running(str(tmp_path)))
        body = sup.overlay_config.read_text()
        assert "[gateway]" in body
        assert "enabled = false" in body
        assert (sup.overlay_config.stat().st_mode & 0o777) == 0o600
    finally:
        sup.stop()


def test_stale_pid_file_archived_on_ensure_running(
    monkeypatch, tmp_path, short_inst, fake_jcode_binary
):
    inst = short_inst
    stale = inst / "pid"
    stale.write_text("999999")
    sup = DaemonSupervisor(fake_jcode_binary, inst)
    monkeypatch.setattr(sup, "_has_creds", lambda: True)
    try:
        asyncio.run(sup.ensure_running(str(tmp_path)))
        archived = list(inst.glob("pid.dead.*"))
        assert archived, "expected stale pid to be archived as pid.dead.*"
    finally:
        sup.stop()


def test_ensure_running_idempotent(
    monkeypatch, tmp_path, short_inst, fake_jcode_binary
):
    sup = DaemonSupervisor(fake_jcode_binary, short_inst)
    monkeypatch.setattr(sup, "_has_creds", lambda: True)
    try:
        s1 = asyncio.run(sup.ensure_running(str(tmp_path)))
        pid1 = int(sup.pid_file.read_text())
        s2 = asyncio.run(sup.ensure_running(str(tmp_path)))
        pid2 = int(sup.pid_file.read_text())
        assert s1 == s2
        assert pid1 == pid2
    finally:
        sup.stop()


# ---------------------------------------------------------------------------
# stop / restart
# ---------------------------------------------------------------------------


def test_stop_kills_pid_and_cleans_files(
    monkeypatch, tmp_path, short_inst, fake_jcode_binary
):
    sup = DaemonSupervisor(fake_jcode_binary, short_inst)
    monkeypatch.setattr(sup, "_has_creds", lambda: True)
    asyncio.run(sup.ensure_running(str(tmp_path)))
    pid = int(sup.pid_file.read_text())
    sup.stop(timeout=3.0)
    # Files removed
    assert not sup.pid_file.exists()
    assert not sup.socket_file.exists()
    # Reap the zombie (pytest is its parent here) and confirm exit.
    # On real deploys jcode is double-forked; this reap is a test artifact.
    try:
        wpid, status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        wpid = pid  # already reaped
    # Whether reaped now or earlier, the pid is no longer ours / not running.
    deadline = time.time() + 3
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return
        # If still showing alive, force-reap and re-check.
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return
        time.sleep(0.05)
    pytest.fail(f"pid {pid} still alive after stop()")


def test_stop_is_safe_when_nothing_running(tmp_path):
    sup = DaemonSupervisor("/bin/true", tmp_path / "inst")
    sup.stop()  # no exception


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def test_health_returns_dict_keys_when_stopped(tmp_path):
    sup = DaemonSupervisor("/bin/true", tmp_path / "inst")
    h = sup.health()
    assert set(h.keys()) == {
        "running",
        "pid",
        "started_at",
        "uptime_s",
        "socket",
        "last_log",
    }
    assert h["running"] is False
    assert h["pid"] is None
    assert h["last_log"] is None


def test_health_when_running(
    monkeypatch, tmp_path, short_inst, fake_jcode_binary
):
    sup = DaemonSupervisor(fake_jcode_binary, short_inst)
    monkeypatch.setattr(sup, "_has_creds", lambda: True)
    try:
        asyncio.run(sup.ensure_running(str(tmp_path)))
        h = sup.health()
        assert h["running"] is True
        assert isinstance(h["pid"], int)
        assert h["uptime_s"] is not None and h["uptime_s"] >= 0
        assert h["last_log"] is not None
        assert h["last_log"].endswith(".log")
    finally:
        sup.stop()
