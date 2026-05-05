"""Framework runtime hooks for jcode_harness plugin.

Per AGENTS.plugins.md §2, A0's plugin manager calls ``install()`` after the
plugin is copied into place via the Plugin Hub. Note: when the plugin is
installed manually (e.g., ``git clone`` into ``usr/plugins/`` or developer
checkout), ``install()`` does NOT fire — A0 only calls it from
``plugins/_plugin_installer/helpers/install.py``. For that case, the user
runs ``execute.py`` from the Plugins UI to set up the binary + providers.

Both ``install()`` and ``execute.py`` share the :func:`run_setup` core so
the binary download, smoke test, and provider import always run identical
logic. Cleanup is also exposed through ``execute.py`` via ``--cleanup``.

Setup order in :func:`run_setup` matters:

1. Resolve binary (user-supplied path → existing PATH → download release).
2. Smoke-test ``--version``.
3. Probe ``cargo --version`` to set ``self_dev_available`` for telemetry.
4. Run the provider importer once (idempotent for plugin-prefixed profiles).
5. Persist install metadata under ``<amplihack>/jcode/install.json`` (0600).

Spike 0.6 confirmed ``jcode serve`` refuses to start without a configured
provider, so this hook intentionally does NOT spawn the daemon — first
startup is lazy on the first tool invocation via ``DaemonSupervisor``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from usr.plugins.jcode_harness.helpers.arch import detect_release_asset_target
from usr.plugins.jcode_harness.helpers.daemon import (
    DaemonSupervisor,
    locate_jcode_binary,
)
from usr.plugins.jcode_harness.helpers.download import (
    download_and_verify,
    fetch_latest_release_metadata,
    pick_asset,
)
from usr.plugins.jcode_harness.helpers import notifications as notify
from usr.plugins.jcode_harness.helpers.paths import (
    amplihack_root,
    jcode_runtime_dir,
)
from usr.plugins.jcode_harness.helpers.provider_import import import_a0_providers


INSTALL_TARGET = Path.home() / ".jcode" / "builds" / "stable" / "jcode"


def _install_meta_path() -> Path:
    """Per-host install metadata file (kept outside the per-instance dir)."""
    return amplihack_root() / "jcode" / "install.json"


def _is_overlay_fs(path: Path) -> bool:
    """Heuristic: ``df -T`` reports ``overlay`` (Docker container layer).

    Used to warn operators that ~/.jcode and ~/.amplihack should be mounted
    as volumes for state persistence. Best-effort — failures are silent.
    """
    try:
        out = subprocess.check_output(
            ["df", "-T", str(path)], text=True, timeout=5
        )
        lines = out.strip().split("\n")
        if len(lines) >= 2:
            return "overlay" in lines[1].lower()
    except Exception:
        pass
    return False


def _get_plugin_config() -> dict:
    """Read plugin config — user-supplied ``binary.path`` takes priority.

    Wrapped in try/except so unit tests (which run without the full A0
    framework on the import path) gracefully fall back to ``{}``.
    """
    try:  # pragma: no cover — A0 runtime path
        from helpers import plugins as a0_plugins  # type: ignore[import-not-found]

        return a0_plugins.get_plugin_config("jcode_harness") or {}
    except Exception:
        return {}


def run_setup(report=None) -> dict:
    """Resolve binary + import providers + persist meta. Returns a status dict.

    ``report`` is an optional callable taking ``(level, message)`` where
    level is one of ``"info" | "success" | "warning" | "error"``. If omitted,
    the function runs silently — useful for tests.

    Idempotent. Safe to re-run after a partial failure.

    Returns ``{"ok": bool, "binary_path": str, "version": str,
    "self_dev_available": bool, "imported": list[str], "skipped": dict,
    "warnings": list[str]}``.
    """
    def _say(level: str, msg: str) -> None:
        if report is not None:
            report(level, msg)

    warnings: list[str] = []
    _say("info", "Setting up jcode harness…")

    if _is_overlay_fs(Path.home()):
        warning = (
            "Home directory is on an ephemeral container layer. "
            "Mount ~/.jcode and ~/.amplihack as volumes to persist state."
        )
        warnings.append(warning)
        _say("warning", warning)

    # 0. User-supplied binary path takes priority (offline / air-gapped).
    cfg = _get_plugin_config()
    user_path = (cfg.get("binary") or {}).get("path", "").strip()
    if user_path and Path(user_path).is_file() and os.access(user_path, os.X_OK):
        binary_path = user_path
        _say("success", f"Using user-supplied jcode at {binary_path}")
    elif (existing := locate_jcode_binary()):
        # 1. PATH detect.
        binary_path = existing
        _say("success", f"Found existing jcode at {existing}")
    else:
        # 2. Download release matching host arch.
        _say("info", "Downloading jcode binary…")
        release = fetch_latest_release_metadata()
        target = detect_release_asset_target()
        asset_url, sha_url = pick_asset(release, target)
        download_and_verify(asset_url, sha_url, INSTALL_TARGET)
        binary_path = str(INSTALL_TARGET)
        _say(
            "success",
            f"jcode {release.get('tag_name', '?')} installed at {binary_path}",
        )

    # 3. Smoke test.
    version_line = subprocess.check_output(
        [binary_path, "--version"], text=True, timeout=10
    ).strip()
    _say("info", f"Smoke test: {version_line}")

    # 4. cargo probe — operators with ``cargo`` can run self-dev workflows.
    cargo_present = shutil.which("cargo") is not None
    if cargo_present:
        _say("info", "Rust toolchain detected — self-dev tool available")
    else:
        _say("info", "No Rust toolchain — self-dev tool will be hidden")

    # 5. Provider import (idempotent for plugin-prefixed profiles).
    imported: list[str] = []
    skipped: dict[str, str] = {}
    try:
        result = import_a0_providers(binary_path)
        imported = result.get("imported") or []
        skipped = result.get("skipped") or {}
        if imported:
            _say(
                "success",
                f"Imported {len(imported)} A0 providers as jcode profiles",
            )
        for pid, reason in skipped.items():
            _say("warning", f"Skipped provider '{pid}': {reason}")
    except Exception as e:
        warnings.append(f"Provider import failed: {e}")
        _say("warning", f"Provider import failed: {e}")

    # 6. Persist install meta.
    meta_path = _install_meta_path()
    meta_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    meta_path.write_text(
        json.dumps(
            {
                "binary_path": binary_path,
                "version": version_line,
                "installed_at": int(time.time()),
                "self_dev_available": cargo_present,
            }
        )
    )
    meta_path.chmod(0o600)

    _say("success", "jcode_harness ready")
    return {
        "ok": True,
        "binary_path": binary_path,
        "version": version_line,
        "self_dev_available": cargo_present,
        "imported": imported,
        "skipped": skipped,
        "warnings": warnings,
    }


async def install() -> None:
    """Plugin Hub install hook. Surfaces every step as A0 notifications."""
    def _notify(level: str, msg: str) -> None:
        getattr(notify, level)(msg)

    try:
        run_setup(report=_notify)
    except Exception as e:
        notify.error(f"jcode setup failed: {e}")
        raise


async def pre_update() -> None:
    """Stop the daemon before plugin code is replaced.

    Called by A0's plugin manager before swapping in a new version of the
    plugin. We graceful-stop the daemon so the new code can rebind the
    socket without a stale-pid race.
    """
    bin_path = locate_jcode_binary()
    if bin_path is None:
        notify.info("jcode binary missing; nothing to stop")
        return
    sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
    sup.stop()
    notify.info("jcode daemon stopped for plugin update")


async def maybe_auto_update() -> None:
    """Check for a newer jcode release and update if config allows.

    Called periodically by an opt-in scheduler — never by ``install()`` or
    ``pre_update()``. Cadence is decided by the caller.

    Skip rules:
      - ``binary.auto_update`` is False (default True)
      - install metadata file does not exist (no prior install)
      - latest release tag matches recorded version

    On a real update we stop the daemon first so the binary can be swapped
    without holding an open file handle.
    """
    cfg = _get_plugin_config()
    if not (cfg.get("binary") or {}).get("auto_update", True):
        return
    meta_path = _install_meta_path()
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return
    try:
        release = fetch_latest_release_metadata()
    except Exception as e:
        notify.warning(f"Auto-update check failed: {e}")
        return

    latest_tag = release.get("tag_name", "")
    if latest_tag and latest_tag == meta.get("version", ""):
        return  # already current (best-effort string comparison)

    notify.info(f"Updating jcode to {latest_tag}…")
    target = detect_release_asset_target()
    asset_url, sha_url = pick_asset(release, target)

    # Stop daemon before swapping binary so we don't hold an open fd.
    bin_path = locate_jcode_binary()
    if bin_path:
        try:
            DaemonSupervisor(bin_path, jcode_runtime_dir()).stop()
        except Exception:
            pass

    download_and_verify(asset_url, sha_url, INSTALL_TARGET)
    meta["version"] = latest_tag
    meta["installed_at"] = int(time.time())
    meta_path.write_text(json.dumps(meta))
    meta_path.chmod(0o600)
    notify.success(f"Updated jcode to {latest_tag}")
