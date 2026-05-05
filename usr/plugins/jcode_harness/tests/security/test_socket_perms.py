"""Spec §8.4: socket file must be 0600 and owned by current user.

DaemonSupervisor.is_running() must return False if either condition fails.
These are smoke tests at the security tier, runnable without spawning a real
jcode daemon.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def supervisor(tmp_path: Path):
    from usr.plugins.jcode_harness.helpers.daemon import DaemonSupervisor

    instance_dir = tmp_path / "inst"
    instance_dir.mkdir()
    return DaemonSupervisor(jcode_binary="/bin/sleep", instance_dir=instance_dir)


def test_is_running_false_when_socket_too_loose(supervisor) -> None:
    """0644 socket file → not considered running."""
    supervisor.pid_file.write_text(str(os.getpid()))
    supervisor.socket_file.touch()
    supervisor.socket_file.chmod(0o644)
    assert not supervisor.is_running(), (
        "socket at 0644 must not be considered running"
    )


def test_is_running_true_with_correct_perms(supervisor) -> None:
    """0600 socket + live pid → considered running."""
    supervisor.pid_file.write_text(str(os.getpid()))
    supervisor.socket_file.touch()
    supervisor.socket_file.chmod(0o600)
    # is_running also checks pid liveness via os.kill(pid, 0); pid=os.getpid()
    # is by definition alive.
    assert supervisor.is_running()


def test_is_running_false_when_socket_owned_by_other_uid(
    supervisor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If stat shows a different uid (foreign user), refuse.

    ``Path.stat()`` is read-only on the instance, so we patch ``os.stat`` in
    the daemon helper's module namespace (which is what ``Path.stat`` calls
    under the hood) and intercept lookups for the supervisor's socket path.
    """
    supervisor.pid_file.write_text(str(os.getpid()))
    supervisor.socket_file.touch()
    supervisor.socket_file.chmod(0o600)

    class _ForeignStat:
        st_mode = 0o100600
        st_uid = os.getuid() + 1234

    real_stat = os.stat
    socket_str = str(supervisor.socket_file)

    def fake_stat(target, *a, **kw):
        if str(target) == socket_str:
            return _ForeignStat()
        return real_stat(target, *a, **kw)

    # ``Path.stat()`` calls ``os.stat`` from ``pathlib``'s own ``os`` ref.
    # The os module is frozen and shared, so patching ``os.stat`` directly
    # is the most portable approach.
    monkeypatch.setattr(os, "stat", fake_stat)
    assert not supervisor.is_running()


def test_is_running_false_when_pid_file_missing(supervisor) -> None:
    """Even with a valid socket, missing pid file → not running."""
    supervisor.socket_file.touch()
    supervisor.socket_file.chmod(0o600)
    assert not supervisor.is_running()


def test_is_running_false_when_socket_file_missing(supervisor) -> None:
    """Even with a valid pid, missing socket file → not running."""
    supervisor.pid_file.write_text(str(os.getpid()))
    assert not supervisor.is_running()
