"""Per-instance runtime path resolver for the jcode_harness plugin.

Spec ref: §4.1, §8.4 — every A0 install gets its own
``~/.amplihack/jcode/<instance_id>/`` runtime directory holding the daemon
socket, pid file, per-A0-context ``client_instance_id`` records, and the
overlay config.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from usr.plugins.jcode_harness.helpers.instance import compute_instance_id


def amplihack_root() -> Path:
    """Return the platform-appropriate amplihack data root.

    macOS/Linux: ``~/.amplihack``
    Windows: ``%LOCALAPPDATA%\\amplihack``
    """
    if platform.system() == "Windows":
        return Path(os.environ["LOCALAPPDATA"]) / "amplihack"
    return Path.home() / ".amplihack"


def _ensure_secure_dir(p: Path) -> None:
    """Create ``p`` if missing and force 0700 permissions.

    ``Path.mkdir(mode=...)`` only honours ``mode`` when the directory is being
    created. If a previous run created the directory under a looser umask,
    those perms persist. We chmod unconditionally to enforce 0700.
    """
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    # chmod is a no-op on Windows for POSIX bits, but harmless.
    try:
        p.chmod(0o700)
    except OSError:
        # Some filesystems (FAT, network mounts) reject chmod; the mkdir
        # mode-on-create path is the best we can do there.
        pass


def jcode_runtime_dir(instance_id: str | None = None) -> Path:
    """Return ``<amplihack>/jcode/<instance_id>/`` (creating + chmod 0700)."""
    iid = instance_id or compute_instance_id()
    p = amplihack_root() / "jcode" / iid
    _ensure_secure_dir(p)
    return p


def socket_path(instance_id: str | None = None) -> Path:
    """Return the Unix socket path for the daemon.

    jcode derives its debug socket by replacing a ``.sock`` suffix with
    ``-debug.sock``. The filename must keep that suffix or the debug socket
    resolves to the same path as the main socket and daemon startup fails with
    ``Address already in use``.
    """
    return jcode_runtime_dir(instance_id) / "jcode.sock"


def pid_path(instance_id: str | None = None) -> Path:
    """Return the daemon pid file path."""
    return jcode_runtime_dir(instance_id) / "pid"


def client_instance_persist_path(
    a0_ctx_id: str, instance_id: str | None = None
) -> Path:
    """Return the per-A0-context ``client_instance_id`` JSON path.

    Creates ``<runtime>/sessions/`` at 0700 if missing.
    """
    sessions_dir = jcode_runtime_dir(instance_id) / "sessions"
    _ensure_secure_dir(sessions_dir)
    return sessions_dir / f"{a0_ctx_id}.json"


def overlay_config_path(instance_id: str | None = None) -> Path:
    """Return the path of the per-instance overlay config TOML."""
    return jcode_runtime_dir(instance_id) / "jcode-config.toml"
