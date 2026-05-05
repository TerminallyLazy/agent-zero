"""Unit tests for execute.py — manual cleanup entry point.

Spec ref: §5.2.

execute.py removes the per-instance amplihack runtime directory and,
optionally, the user-data directory at ~/.jcode/.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


def _ensure_framework_notification_stubbed() -> None:
    """Same shim as test_hooks — see that module for the rationale."""
    if "helpers.notification" in sys.modules:
        return
    parent = sys.modules.get("helpers")
    if parent is None:
        parent = types.ModuleType("helpers")
        parent.__path__ = []  # type: ignore[attr-defined]
        sys.modules["helpers"] = parent

    mod = types.ModuleType("helpers.notification")

    class _Stub:
        @staticmethod
        def send_notification(**_kw):
            pass

    class _Enum:
        INFO = "info"
        SUCCESS = "success"
        WARNING = "warning"
        ERROR = "error"
        NORMAL = "normal"

    mod.NotificationManager = _Stub  # type: ignore[attr-defined]
    mod.NotificationPriority = _Enum  # type: ignore[attr-defined]
    mod.NotificationType = _Enum  # type: ignore[attr-defined]
    sys.modules["helpers.notification"] = mod
    setattr(parent, "notification", mod)


_ensure_framework_notification_stubbed()


@pytest.fixture
def runtime_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, Path]:
    """Lay out fake amplihack + jcode user-data dirs under tmp_path.

    Patches ``Path.home()`` so any direct ``Path.home() / '.jcode'`` calls
    inside execute.py resolve under tmp_path. Patches
    ``jcode_runtime_dir`` to return a deterministic per-test instance dir.
    """
    instance_dir = tmp_path / ".amplihack" / "jcode" / "test-instance"
    instance_dir.mkdir(parents=True)
    (instance_dir / "marker").write_text("amplihack")

    user_data = tmp_path / ".jcode"
    user_data.mkdir()
    (user_data / "marker").write_text("user-data")

    from usr.plugins.jcode_harness.helpers import paths as paths_mod

    monkeypatch.setattr(
        paths_mod.Path, "home", classmethod(lambda cls: tmp_path)
    )
    monkeypatch.setattr(paths_mod.platform, "system", lambda: "Darwin")

    # execute.py also calls Path.home() directly.
    from usr.plugins.jcode_harness import execute as execute_mod

    monkeypatch.setattr(
        execute_mod.Path, "home", classmethod(lambda cls: tmp_path)
    )

    # jcode_runtime_dir() defaults to compute_instance_id(); pin it.
    from usr.plugins.jcode_harness.helpers import paths as paths_mod_again

    monkeypatch.setattr(
        paths_mod_again, "jcode_runtime_dir", lambda *_a, **_kw: instance_dir
    )

    return {
        "instance": instance_dir,
        "user_data": user_data,
        "tmp": tmp_path,
    }


def test_cleanup_removes_amplihack_dir_only_by_default(
    runtime_layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from usr.plugins.jcode_harness import execute as execute_mod

    # Avoid the daemon-stop branch
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.daemon.locate_jcode_binary",
        lambda: None,
    )

    rc = execute_mod.main(also_delete_user_data=False)

    assert rc == 0
    assert not runtime_layout["instance"].exists()
    assert runtime_layout["user_data"].exists()  # preserved


def test_cleanup_removes_user_data_when_flagged(
    runtime_layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from usr.plugins.jcode_harness import execute as execute_mod

    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.daemon.locate_jcode_binary",
        lambda: None,
    )

    rc = execute_mod.main(also_delete_user_data=True)

    assert rc == 0
    assert not runtime_layout["instance"].exists()
    assert not runtime_layout["user_data"].exists()


def test_cleanup_calls_daemon_stop(
    runtime_layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from usr.plugins.jcode_harness import execute as execute_mod

    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.daemon.locate_jcode_binary",
        lambda: "/bin/jcode",
    )

    stop_calls = []

    class _FakeSup:
        def __init__(self, bin_path, instance_dir):
            self.bin_path = bin_path
            self.instance_dir = instance_dir

        def stop(self):
            stop_calls.append(1)

    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.daemon.DaemonSupervisor",
        _FakeSup,
    )

    rc = execute_mod.main(also_delete_user_data=False)

    assert rc == 0
    assert stop_calls == [1]


def test_cleanup_handles_missing_amplihack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from usr.plugins.jcode_harness.helpers import paths as paths_mod
    from usr.plugins.jcode_harness import execute as execute_mod

    instance_dir = tmp_path / ".amplihack" / "jcode" / "missing"

    monkeypatch.setattr(
        paths_mod.Path, "home", classmethod(lambda cls: tmp_path)
    )
    monkeypatch.setattr(paths_mod.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        execute_mod.Path, "home", classmethod(lambda cls: tmp_path)
    )
    monkeypatch.setattr(
        paths_mod, "jcode_runtime_dir", lambda *_a, **_kw: instance_dir
    )
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.daemon.locate_jcode_binary",
        lambda: None,
    )

    rc = execute_mod.main(also_delete_user_data=False)
    assert rc == 0


def test_cleanup_handles_missing_binary(
    runtime_layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from usr.plugins.jcode_harness import execute as execute_mod

    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.daemon.locate_jcode_binary",
        lambda: None,
    )

    sentinel = []

    class _FakeSup:
        def __init__(self, *_a, **_kw):
            sentinel.append("ctor")

        def stop(self):
            sentinel.append("stop")

    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.daemon.DaemonSupervisor",
        _FakeSup,
    )

    rc = execute_mod.main(also_delete_user_data=False)

    assert rc == 0
    assert sentinel == []  # supervisor never constructed
