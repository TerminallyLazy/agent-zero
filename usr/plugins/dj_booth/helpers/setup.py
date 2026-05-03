"""System dependency bootstrap for dj_booth.

A0 doesn't automatically call hooks.py:install() on plugin install — only
uninstall() runs automatically. So we bootstrap on first Execute by calling
ensure_dependencies(), which is idempotent: if everything's already there,
it returns immediately.

Designed for non-technical users: every message is plain language and prints
to stdout so it surfaces in the Plugin Execute log in the A0 UI.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import List, Tuple


# ffmpeg is the ONLY required binary — the streaming server is pure Python
# (helpers/icy_server.py) and runs in-process. icecast2 and liquidsoap are
# optional upgrades the booth uses when present.
REQUIRED_BINARIES = ("ffmpeg",)
PREFERRED_BINARIES = ("icecast2", "liquidsoap")  # missing → in-process Python server + ffmpeg-only mode

REQUIRED_PY = ("mutagen",)
PREFERRED_PY = ("numpy", "scipy", "aubio")  # analysis features — not fatal if missing

APT_PACKAGES = ["ffmpeg"]
APT_OPTIONAL = ["icecast2", "liquidsoap", "libaubio-dev", "libsndfile1"]
PIP_PACKAGES = ["mutagen>=1.47", "requests>=2.31"]
PIP_OPTIONAL = ["numpy>=1.24", "scipy>=1.11", "aubio>=0.4.9", "pyaudio>=0.2.14"]

DEBCONF_PRESEED = """\
icecast2 icecast2/icecast-setup boolean false
icecast2 icecast2/icecast-setup-message note
"""


def _have_binary(name: str) -> bool:
    return shutil.which(name) is not None


def _have_python_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _missing_binaries() -> List[str]:
    return [b for b in REQUIRED_BINARIES if not _have_binary(b)]


def _missing_required_py() -> List[str]:
    return [m for m in REQUIRED_PY if not _have_python_module(m)]


def _have_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _run(cmd: List[str], env: dict | None = None) -> Tuple[int, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
        return result.returncode, (result.stderr or result.stdout or "")
    except FileNotFoundError as e:
        return 127, str(e)
    except Exception as e:
        return -1, str(e)


def _apt_install(packages: List[str]) -> Tuple[bool, str]:
    """Install apt packages with non-interactive frontend + debconf preseed
    so icecast2's setup wizard doesn't hang."""
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"

    # Preseed icecast2 to skip its interactive setup
    try:
        proc = subprocess.run(
            ["debconf-set-selections"],
            input=DEBCONF_PRESEED, text=True,
            capture_output=True, timeout=15,
        )
        if proc.returncode != 0:
            print(f"[DJ Booth]  (debconf preseed warning, continuing): {proc.stderr.strip()[:200]}")
    except FileNotFoundError:
        pass  # debconf-set-selections not present — apt may still work

    # Try update first (cheap if cache is fresh)
    rc, _out = _run(["apt-get", "update", "-qq"], env=env)
    if rc != 0:
        # Not fatal — install can still succeed if cache is recent enough
        pass

    cmd = ["apt-get", "install", "-y", "-qq", "--no-install-recommends"] + packages
    rc, out = _run(cmd, env=env)
    return rc == 0, out


def _pip_install(packages: List[str]) -> Tuple[bool, str]:
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check"] + packages
    rc, out = _run(cmd)
    return rc == 0, out


def ensure_dependencies(verbose: bool = True) -> dict:
    """
    Idempotent dependency check + install. Returns a dict with status info.
    Safe to call on every Execute — a no-op when everything's already there.
    """
    status = {
        "ok": False,
        "missing_binaries": [],
        "missing_python": [],
        "messages": [],
        "needs_manual_install": False,
    }

    def say(msg):
        status["messages"].append(msg)
        if verbose:
            print(f"[DJ Booth] {msg}")

    missing_bin = _missing_binaries()
    missing_py = _missing_required_py()

    if not missing_bin and not missing_py:
        status["ok"] = True
        say("All required components are installed.")
        return status

    say("First-time setup — installing the radio stack. This takes a minute or two on first run.")

    if missing_bin:
        if not _have_root():
            say("Cannot auto-install system packages without root access.")
            say(f"Please ask whoever set up Agent Zero to run: apt-get install {' '.join(APT_PACKAGES)}")
            status["needs_manual_install"] = True
            status["missing_binaries"] = missing_bin
            return status

        say("Installing audio encoder (FFmpeg)...")
        ok, out = _apt_install(APT_PACKAGES)
        if not ok:
            tail = out.strip().splitlines()[-3:] if out else []
            say(f"FFmpeg install ran into trouble: {' / '.join(tail) if tail else 'unknown error'}")
            status["missing_binaries"] = _missing_binaries()
            if status["missing_binaries"]:
                status["needs_manual_install"] = True
                return status
        else:
            say("Audio encoder installed.")

        # Optional upgrades — try but don't block on failure.
        # Built-in Python streaming server covers the icecast2 case.
        # Without liquidsoap the booth runs in single-deck/sequential mode.
        missing_optional = [p for p in APT_OPTIONAL if not _have_binary(p.split('-')[0])]
        if missing_optional:
            say("Trying optional upgrades (icecast2, liquidsoap, audio analysis libs)...")
            ok_opt, _ = _apt_install(APT_OPTIONAL)
            if ok_opt:
                say("Optional upgrades installed — full feature set available.")
            else:
                say("Optional upgrades not available in this image — booth runs in basic mode (single deck, built-in streaming server). All listener-facing features still work.")

    # Re-check
    missing_bin = _missing_binaries()
    if missing_bin:
        say(f"Still missing: {', '.join(missing_bin)}. Setup cannot continue.")
        status["missing_binaries"] = missing_bin
        status["needs_manual_install"] = True
        return status

    if missing_py:
        say("Installing Python helpers (track tags, analysis)...")
        ok, out = _pip_install(PIP_PACKAGES)
        if not ok:
            say(f"Python helper install hit a snag — some features may be limited.")
        else:
            say("Python helpers installed.")

    # Optional packages — best-effort, non-fatal
    for opt_pkg in PIP_OPTIONAL:
        mod = opt_pkg.split(">=")[0].split("==")[0]
        if not _have_python_module(mod):
            ok, _ = _pip_install([opt_pkg])
            if not ok and verbose:
                say(f"Optional component '{mod}' skipped (the booth still works without it).")

    music_dir = "/a0/usr/workdir/music"
    try:
        os.makedirs(music_dir, exist_ok=True)
    except Exception:
        pass

    status["missing_binaries"] = _missing_binaries()
    status["missing_python"] = _missing_required_py()
    status["ok"] = not status["missing_binaries"] and not status["missing_python"]
    if status["ok"]:
        say("Setup complete. Starting the stream...")
    else:
        say("Setup did not fully complete. See messages above.")
        status["needs_manual_install"] = True
    return status
