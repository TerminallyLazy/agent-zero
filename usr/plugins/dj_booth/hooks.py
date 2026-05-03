"""Plugin install/uninstall hooks for dj_booth."""
import os
import subprocess
import sys


def install():
    print("[dj_booth] installing system packages (icecast2, liquidsoap, ffmpeg, libaubio-dev, libsndfile1, portaudio19-dev)...")
    apt_packages = [
        "icecast2", "liquidsoap", "ffmpeg",
        "libaubio-dev", "libsndfile1", "portaudio19-dev",
    ]
    result = subprocess.run(
        ["apt-get", "install", "-y", "--no-install-recommends"] + apt_packages,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[dj_booth] WARNING: apt install failed (continuing): {result.stderr}")
    else:
        print("[dj_booth] system packages installed.")

    print("[dj_booth] installing python packages...")
    py_packages = [
        "mutagen>=1.47", "requests>=2.31",
        "aubio>=0.4.9", "numpy>=1.24", "scipy>=1.11",
    ]
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet"] + py_packages,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[dj_booth] WARNING: pip install failed: {result.stderr}")
    else:
        print("[dj_booth] python packages installed.")

    # pyaudio install can fail without portaudio — isolate so other packages don't roll back.
    print("[dj_booth] installing pyaudio (best-effort, mic capture)...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "pyaudio>=0.2.14"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[dj_booth] WARNING: pyaudio install failed (mic disabled): {result.stderr.strip()}")
    else:
        print("[dj_booth] pyaudio installed.")

    music_dir = "/a0/usr/workdir/music"
    os.makedirs(music_dir, exist_ok=True)
    print(f"[dj_booth] music directory ready: {music_dir}")
    print("[dj_booth] install complete.")


def uninstall():
    print("[dj_booth] uninstalling — stopping services...")
    try:
        import asyncio
        from usr.plugins.dj_booth.helpers.lifecycle import stop_stack
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(stop_stack())
            else:
                loop.run_until_complete(stop_stack())
        except RuntimeError:
            asyncio.run(stop_stack())
    except Exception as e:
        print(f"[dj_booth] uninstall warning: {e}")
    print("[dj_booth] uninstall complete.")
