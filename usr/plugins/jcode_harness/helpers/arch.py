"""Detect host arch for jcode release-asset selection.

Spec ref: §5.2 — release downloader chooses the correct GitHub asset for the
current host. Verified asset naming against jcode v0.11.10:
``jcode-{macos|linux|windows}-{aarch64|x86_64}.{tar.gz|exe}``.
"""

from __future__ import annotations

import platform
import subprocess


def detect_release_asset_target() -> str:
    """Return the asset suffix for the running host.

    One of:
      ``macos-aarch64``, ``macos-x86_64``,
      ``linux-aarch64``, ``linux-x86_64``,
      ``windows-aarch64``, ``windows-x86_64``.

    On macOS we consult ``sysctl hw.optional.arm64`` to detect Apple Silicon
    even when running under Rosetta (where ``platform.machine()`` reports
    ``x86_64``).
    """
    sys = platform.system()
    if sys == "Darwin":
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.optional.arm64"],
                stderr=subprocess.DEVNULL,
            ).strip()
            if out == b"1":
                return "macos-aarch64"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        return "macos-x86_64"
    if sys == "Linux":
        m = platform.machine().lower()
        if m in {"aarch64", "arm64"}:
            return "linux-aarch64"
        return "linux-x86_64"
    if sys == "Windows":
        m = platform.machine().lower()
        if m in {"aarch64", "arm64"}:
            return "windows-aarch64"
        return "windows-x86_64"
    raise RuntimeError(f"unsupported OS: {sys}")
