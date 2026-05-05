"""Unit tests for hooks.py — install(), pre_update(), maybe_auto_update().

Spec ref: §5.2. Plan ref: Chunk 5.

All filesystem and network access is mocked; tests must never reach
``api.github.com``, the real ``~/.jcode``, or the real ``~/.amplihack``.
"""

from __future__ import annotations

import asyncio
import json
import stat
import sys
import types
from pathlib import Path

import pytest


def _ensure_framework_notification_stubbed() -> None:
    """Make ``helpers.notification`` importable so hooks.py can be loaded.

    The plugin tree shadows the A0 framework's top-level ``helpers/`` package
    on sys.path (see test_notifications.py for the underlying explanation).
    The simplest workaround for unit tests that don't actually exercise the
    notification side-effects is to inject a no-op module under
    ``helpers.notification``. The recorder fixture replaces ``hooks.notify``
    with its own object anyway.
    """
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


# ---------------------------------------------------------------------------
# Notification recorder — replaces the helpers.notifications module so the
# A0 framework dependency does not have to be reachable in unit tests.
# ---------------------------------------------------------------------------


class _NotifyRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def info(self, msg: str, title: str = "jcode") -> None:
        self.events.append(("info", msg))

    def success(self, msg: str, title: str = "jcode") -> None:
        self.events.append(("success", msg))

    def warning(self, msg: str, title: str = "jcode") -> None:
        self.events.append(("warning", msg))

    def error(self, msg: str, title: str = "jcode") -> None:
        self.events.append(("error", msg))


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() and the amplihack root into tmp_path."""
    from usr.plugins.jcode_harness.helpers import paths as paths_mod

    monkeypatch.setattr(
        paths_mod.Path, "home", classmethod(lambda cls: tmp_path)
    )
    monkeypatch.setattr(paths_mod.platform, "system", lambda: "Darwin")
    return tmp_path


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _NotifyRecorder:
    """Patch the hooks module's notify reference to a recorder."""
    from usr.plugins.jcode_harness import hooks as hooks_mod

    rec = _NotifyRecorder()
    monkeypatch.setattr(hooks_mod, "notify", rec)
    return rec


@pytest.fixture
def fake_binary(tmp_path: Path) -> Path:
    """A real on-disk executable file we can hand to install() as user-supplied."""
    bin_path = tmp_path / "fake-jcode"
    bin_path.write_text("#!/bin/sh\necho jcode 9.9.9\n")
    bin_path.chmod(0o755)
    return bin_path


def _patch_hooks_path_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Patch Path.home() inside the hooks module's namespace.

    install() also uses Path.home() directly to compute INSTALL_TARGET; we want
    that to live under tmp_path too.
    """
    from usr.plugins.jcode_harness import hooks as hooks_mod

    monkeypatch.setattr(
        hooks_mod.Path, "home", classmethod(lambda cls: tmp_path)
    )
    # Re-bind INSTALL_TARGET because module-level Path.home() was already evaluated.
    monkeypatch.setattr(
        hooks_mod,
        "INSTALL_TARGET",
        tmp_path / ".jcode" / "builds" / "stable" / "jcode",
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# install()
# ---------------------------------------------------------------------------


def test_install_uses_user_supplied_binary_path(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    fake_binary: Path,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)

    monkeypatch.setattr(hooks_mod, "_is_overlay_fs", lambda p: False)
    monkeypatch.setattr(
        hooks_mod, "_get_plugin_config",
        lambda: {"binary": {"path": str(fake_binary)}},
    )
    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: None)

    fetch_called = []
    monkeypatch.setattr(
        hooks_mod,
        "fetch_latest_release_metadata",
        lambda: fetch_called.append(1) or {},
    )
    monkeypatch.setattr(
        hooks_mod, "subprocess",
        type("S", (), {
            "check_output": staticmethod(
                lambda *a, **kw: "jcode 9.9.9"
            ),
        })(),
    )
    monkeypatch.setattr(
        hooks_mod, "import_a0_providers",
        lambda b: {"imported": [], "skipped": {}},
    )
    monkeypatch.setattr(hooks_mod.shutil, "which", lambda name: None)

    _run(hooks_mod.install())

    # Download path was NEVER invoked
    assert fetch_called == []
    # success notification mentioning the user-supplied binary
    assert any("user-supplied" in m for kind, m in recorder.events if kind == "success")


def test_install_uses_existing_path_binary(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)

    monkeypatch.setattr(hooks_mod, "_is_overlay_fs", lambda p: False)
    monkeypatch.setattr(hooks_mod, "_get_plugin_config", lambda: {})
    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: "/usr/local/bin/jcode")

    fetch_called = []
    monkeypatch.setattr(
        hooks_mod,
        "fetch_latest_release_metadata",
        lambda: fetch_called.append(1) or {},
    )
    monkeypatch.setattr(
        hooks_mod, "subprocess",
        type("S", (), {
            "check_output": staticmethod(lambda *a, **kw: "jcode 1.2.3"),
        })(),
    )
    monkeypatch.setattr(
        hooks_mod, "import_a0_providers",
        lambda b: {"imported": [], "skipped": {}},
    )
    monkeypatch.setattr(hooks_mod.shutil, "which", lambda name: None)

    _run(hooks_mod.install())

    assert fetch_called == []
    assert any("Found existing jcode" in m for _, m in recorder.events)


def test_install_downloads_when_no_binary_found(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)

    monkeypatch.setattr(hooks_mod, "_is_overlay_fs", lambda p: False)
    monkeypatch.setattr(hooks_mod, "_get_plugin_config", lambda: {})
    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: None)

    monkeypatch.setattr(
        hooks_mod,
        "fetch_latest_release_metadata",
        lambda: {"tag_name": "v0.11.10", "assets": []},
    )
    monkeypatch.setattr(hooks_mod, "detect_release_asset_target", lambda: "macos-aarch64")
    pick_calls = []
    monkeypatch.setattr(
        hooks_mod, "pick_asset",
        lambda r, t: pick_calls.append((r, t)) or ("u1", "u2"),
    )
    download_calls = []
    monkeypatch.setattr(
        hooks_mod, "download_and_verify",
        lambda a, s, p: download_calls.append((a, s, p)),
    )
    monkeypatch.setattr(
        hooks_mod, "subprocess",
        type("S", (), {
            "check_output": staticmethod(lambda *a, **kw: "jcode 0.11.10"),
        })(),
    )
    monkeypatch.setattr(
        hooks_mod, "import_a0_providers",
        lambda b: {"imported": [], "skipped": {}},
    )
    monkeypatch.setattr(hooks_mod.shutil, "which", lambda name: None)

    _run(hooks_mod.install())

    assert len(pick_calls) == 1
    assert len(download_calls) == 1
    # download target == INSTALL_TARGET (under tmp_path)
    assert download_calls[0][2] == hooks_mod.INSTALL_TARGET


def test_install_writes_install_meta(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    fake_binary: Path,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)

    monkeypatch.setattr(hooks_mod, "_is_overlay_fs", lambda p: False)
    monkeypatch.setattr(
        hooks_mod, "_get_plugin_config",
        lambda: {"binary": {"path": str(fake_binary)}},
    )
    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: None)
    monkeypatch.setattr(
        hooks_mod, "subprocess",
        type("S", (), {
            "check_output": staticmethod(lambda *a, **kw: "jcode 9.9.9"),
        })(),
    )
    monkeypatch.setattr(
        hooks_mod, "import_a0_providers",
        lambda b: {"imported": [], "skipped": {}},
    )
    monkeypatch.setattr(hooks_mod.shutil, "which", lambda name: "/usr/bin/cargo")

    _run(hooks_mod.install())

    meta_path = hooks_mod._install_meta_path()
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["binary_path"] == str(fake_binary)
    assert meta["version"] == "jcode 9.9.9"
    assert isinstance(meta["installed_at"], int)
    assert meta["self_dev_available"] is True
    # 0600 perms
    mode = stat.S_IMODE(meta_path.stat().st_mode)
    assert mode == 0o600


def test_install_self_dev_flag_reflects_cargo_presence(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    fake_binary: Path,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)

    monkeypatch.setattr(hooks_mod, "_is_overlay_fs", lambda p: False)
    monkeypatch.setattr(
        hooks_mod, "_get_plugin_config",
        lambda: {"binary": {"path": str(fake_binary)}},
    )
    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: None)
    monkeypatch.setattr(
        hooks_mod, "subprocess",
        type("S", (), {
            "check_output": staticmethod(lambda *a, **kw: "jcode 1.0.0"),
        })(),
    )
    monkeypatch.setattr(
        hooks_mod, "import_a0_providers",
        lambda b: {"imported": [], "skipped": {}},
    )

    monkeypatch.setattr(hooks_mod.shutil, "which", lambda name: None)
    _run(hooks_mod.install())
    meta = json.loads(hooks_mod._install_meta_path().read_text())
    assert meta["self_dev_available"] is False

    monkeypatch.setattr(hooks_mod.shutil, "which", lambda name: "/usr/bin/cargo")
    _run(hooks_mod.install())
    meta = json.loads(hooks_mod._install_meta_path().read_text())
    assert meta["self_dev_available"] is True


def test_install_swallows_provider_import_failure(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    fake_binary: Path,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)

    monkeypatch.setattr(hooks_mod, "_is_overlay_fs", lambda p: False)
    monkeypatch.setattr(
        hooks_mod, "_get_plugin_config",
        lambda: {"binary": {"path": str(fake_binary)}},
    )
    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: None)
    monkeypatch.setattr(
        hooks_mod, "subprocess",
        type("S", (), {
            "check_output": staticmethod(lambda *a, **kw: "jcode 1.0.0"),
        })(),
    )

    def _boom(*_a, **_kw):
        raise RuntimeError("provider import boom")

    monkeypatch.setattr(hooks_mod, "import_a0_providers", _boom)
    monkeypatch.setattr(hooks_mod.shutil, "which", lambda name: None)

    # Must not raise
    _run(hooks_mod.install())

    # warning recorded mentioning the failure
    assert any("provider import" in m.lower() or "boom" in m.lower()
               for kind, m in recorder.events if kind == "warning")
    # install metadata still written
    assert hooks_mod._install_meta_path().exists()


def test_install_warns_on_overlay_fs(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    fake_binary: Path,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)

    monkeypatch.setattr(hooks_mod, "_is_overlay_fs", lambda p: True)
    monkeypatch.setattr(
        hooks_mod, "_get_plugin_config",
        lambda: {"binary": {"path": str(fake_binary)}},
    )
    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: None)
    monkeypatch.setattr(
        hooks_mod, "subprocess",
        type("S", (), {
            "check_output": staticmethod(lambda *a, **kw: "jcode 1.0.0"),
        })(),
    )
    monkeypatch.setattr(
        hooks_mod, "import_a0_providers",
        lambda b: {"imported": [], "skipped": {}},
    )
    monkeypatch.setattr(hooks_mod.shutil, "which", lambda name: None)

    _run(hooks_mod.install())

    assert any(
        "ephemeral" in m.lower() or "overlay" in m.lower() or "volume" in m.lower()
        for kind, m in recorder.events if kind == "warning"
    )


# ---------------------------------------------------------------------------
# pre_update()
# ---------------------------------------------------------------------------


def test_pre_update_calls_stop_when_binary_present(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: "/bin/jcode")

    stop_calls = []

    class _FakeSup:
        def __init__(self, bin_path, instance_dir):
            self.bin_path = bin_path
            self.instance_dir = instance_dir

        def stop(self):
            stop_calls.append(1)

    monkeypatch.setattr(hooks_mod, "DaemonSupervisor", _FakeSup)

    _run(hooks_mod.pre_update())

    assert stop_calls == [1]
    assert any("stopped" in m.lower() for kind, m in recorder.events if kind == "info")


def test_pre_update_skips_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: None)

    sentinel = []

    class _FakeSup:
        def __init__(self, *_a, **_kw):
            sentinel.append("constructed")

        def stop(self):
            sentinel.append("stopped")

    monkeypatch.setattr(hooks_mod, "DaemonSupervisor", _FakeSup)

    _run(hooks_mod.pre_update())

    assert sentinel == []  # never constructed, never stopped
    assert any(
        "missing" in m.lower() or "nothing" in m.lower()
        for kind, m in recorder.events if kind == "info"
    )


# ---------------------------------------------------------------------------
# maybe_auto_update()
# ---------------------------------------------------------------------------


def _seed_meta(hooks_mod, version: str) -> Path:
    meta = hooks_mod._install_meta_path()
    meta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    meta.write_text(
        json.dumps(
            {
                "binary_path": "/bin/jcode",
                "version": version,
                "installed_at": 0,
                "self_dev_available": False,
            }
        )
    )
    meta.chmod(0o600)
    return meta


def test_auto_update_skipped_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)

    monkeypatch.setattr(
        hooks_mod, "_get_plugin_config",
        lambda: {"binary": {"auto_update": False}},
    )

    fetch_calls = []
    monkeypatch.setattr(
        hooks_mod, "fetch_latest_release_metadata",
        lambda: fetch_calls.append(1) or {},
    )

    _run(hooks_mod.maybe_auto_update())
    assert fetch_calls == []


def test_auto_update_skipped_when_no_meta(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)

    monkeypatch.setattr(hooks_mod, "_get_plugin_config", lambda: {})
    fetch_calls = []
    monkeypatch.setattr(
        hooks_mod, "fetch_latest_release_metadata",
        lambda: fetch_calls.append(1) or {},
    )

    # Ensure meta does not exist
    assert not hooks_mod._install_meta_path().exists()

    _run(hooks_mod.maybe_auto_update())
    assert fetch_calls == []


def test_auto_update_skipped_when_already_current(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)
    monkeypatch.setattr(hooks_mod, "_get_plugin_config", lambda: {})

    _seed_meta(hooks_mod, "v0.11.10")
    monkeypatch.setattr(
        hooks_mod, "fetch_latest_release_metadata",
        lambda: {"tag_name": "v0.11.10", "assets": []},
    )
    download_calls = []
    monkeypatch.setattr(
        hooks_mod, "download_and_verify",
        lambda *a, **kw: download_calls.append(a),
    )

    _run(hooks_mod.maybe_auto_update())
    assert download_calls == []


def test_auto_update_runs_when_version_differs(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)
    monkeypatch.setattr(hooks_mod, "_get_plugin_config", lambda: {})

    meta_path = _seed_meta(hooks_mod, "v0.11.9")

    monkeypatch.setattr(
        hooks_mod, "fetch_latest_release_metadata",
        lambda: {"tag_name": "v0.11.10", "assets": []},
    )
    monkeypatch.setattr(hooks_mod, "detect_release_asset_target", lambda: "macos-aarch64")
    monkeypatch.setattr(hooks_mod, "pick_asset", lambda r, t: ("u1", "u2"))
    download_calls = []
    monkeypatch.setattr(
        hooks_mod, "download_and_verify",
        lambda a, s, p: download_calls.append((a, s, p)),
    )
    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: None)

    _run(hooks_mod.maybe_auto_update())

    assert len(download_calls) == 1
    new_meta = json.loads(meta_path.read_text())
    assert new_meta["version"] == "v0.11.10"
    # 0600 perms preserved
    assert stat.S_IMODE(meta_path.stat().st_mode) == 0o600


def test_auto_update_swallows_fetch_failure(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)
    monkeypatch.setattr(hooks_mod, "_get_plugin_config", lambda: {})
    _seed_meta(hooks_mod, "v0.11.9")

    def _boom():
        raise RuntimeError("github down")

    monkeypatch.setattr(hooks_mod, "fetch_latest_release_metadata", _boom)

    # Must not raise
    _run(hooks_mod.maybe_auto_update())

    assert any(
        "auto-update" in m.lower() or "github down" in m.lower()
        for kind, m in recorder.events if kind == "warning"
    )


def test_auto_update_stops_daemon_before_swap(
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    recorder: _NotifyRecorder,
    tmp_path: Path,
) -> None:
    from usr.plugins.jcode_harness import hooks as hooks_mod

    _patch_hooks_path_home(monkeypatch, tmp_path)
    monkeypatch.setattr(hooks_mod, "_get_plugin_config", lambda: {})
    _seed_meta(hooks_mod, "v0.11.9")

    monkeypatch.setattr(
        hooks_mod, "fetch_latest_release_metadata",
        lambda: {"tag_name": "v0.11.10", "assets": []},
    )
    monkeypatch.setattr(hooks_mod, "detect_release_asset_target", lambda: "macos-aarch64")
    monkeypatch.setattr(hooks_mod, "pick_asset", lambda r, t: ("u1", "u2"))

    order: list[str] = []

    def _download(a, s, p):
        order.append("download")

    monkeypatch.setattr(hooks_mod, "download_and_verify", _download)
    monkeypatch.setattr(hooks_mod, "locate_jcode_binary", lambda: "/bin/jcode")

    class _FakeSup:
        def __init__(self, *_a, **_kw):
            pass

        def stop(self):
            order.append("stop")

    monkeypatch.setattr(hooks_mod, "DaemonSupervisor", _FakeSup)

    _run(hooks_mod.maybe_auto_update())

    assert order == ["stop", "download"]
