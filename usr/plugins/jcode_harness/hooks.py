"""Framework runtime hooks for jcode_harness plugin.

Per AGENTS.plugins.md §2, A0's plugin manager calls ``install()`` after the
plugin is copied into place and ``pre_update()`` before plugin code is
replaced. Both may be sync or async; async is awaited. Cleanup lives in
``execute.py`` (Spec §5.2) so it can be re-run after plugin removal.

The order in :func:`install` matters:

1. Resolve binary (user-supplied path → existing PATH → download release).
2. Smoke-test ``--version``.
3. Probe ``cargo --version`` to set ``self_dev_available`` for telemetry.
4. Run the provider importer once (idempotent for plugin-prefixed profiles).
5. Persist install metadata under ``<amplihack>/jcode/install.json`` (0600).
6. Surface every step via the A0 notification helper.

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


async def install() -> None:
    """Set up the jcode binary + provider profiles. Called by A0 plugin mgr."""
    notify.info("Setting up jcode harness…")

    if _is_overlay_fs(Path.home()):
        notify.warning(
            "Home directory is on an ephemeral container layer. "
            "Mount ~/.jcode and ~/.amplihack as volumes to persist state."
        )

    # 0. User-supplied binary path takes priority (offline / air-gapped).
    cfg = _get_plugin_config()
    user_path = (cfg.get("binary") or {}).get("path", "").strip()
    if user_path and Path(user_path).is_file() and os.access(user_path, os.X_OK):
        binary_path = user_path
        notify.success(f"Using user-supplied jcode at {binary_path}")
    elif (existing := locate_jcode_binary()):
        # 1. PATH detect.
        binary_path = existing
        notify.success(f"Found existing jcode at {existing}")
    else:
        # 2. Download release matching host arch.
        notify.info("Downloading jcode binary…")
        release = fetch_latest_release_metadata()
        target = detect_release_asset_target()
        asset_url, sha_url = pick_asset(release, target)
        download_and_verify(asset_url, sha_url, INSTALL_TARGET)
        binary_path = str(INSTALL_TARGET)
        notify.success(
            f"jcode {release.get('tag_name', '?')} installed at {binary_path}"
        )

    # 3. Smoke test.
    out = subprocess.check_output(
        [binary_path, "--version"], text=True, timeout=10
    ).strip()
    notify.info(f"Smoke test: {out}")

    # 4. cargo probe — operators with ``cargo`` can run self-dev workflows.
    cargo_present = shutil.which("cargo") is not None

    # 5. Provider import (idempotent for plugin-prefixed profiles).
    try:
        result = import_a0_providers(binary_path)
        if result.get("imported"):
            notify.success(
                f"Imported {len(result['imported'])} A0 providers as jcode profiles"
            )
        for pid, reason in (result.get("skipped") or {}).items():
            notify.warning(f"Skipped provider '{pid}': {reason}")
    except Exception as e:
        notify.warning(f"Provider import failed: {e}")

    # 6. Persist install meta.
    meta_path = _install_meta_path()
    meta_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    meta_path.write_text(
        json.dumps(
            {
                "binary_path": binary_path,
                "version": out,
                "installed_at": int(time.time()),
                "self_dev_available": cargo_present,
            }
        )
    )
    meta_path.chmod(0o600)

    notify.success("jcode_harness ready")


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
