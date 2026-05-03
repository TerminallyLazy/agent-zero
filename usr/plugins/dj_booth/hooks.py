"""Plugin install/uninstall hooks for dj_booth.

NOTE: every print() call below appears in the Plugin Install log surfaced
by the Agent Zero UI when the user installs DJ Booth. Keep messages short
and plain-language so non-technical users see friendly progress instead
of opaque package lists.
"""
import os
import subprocess
import sys


def install():
    # User-visible progress in the Plugin Install log:
    print("[DJ Booth] Setting up the radio stack — this can take a minute...")
    print("[DJ Booth] Step 1/3: installing audio system tools (Icecast, Liquidsoap, FFmpeg, audio libs)")
    apt_packages = [
        "icecast2", "liquidsoap", "ffmpeg",
        "libaubio-dev", "libsndfile1", "portaudio19-dev",
    ]
    result = subprocess.run(
        ["apt-get", "install", "-y", "--no-install-recommends"] + apt_packages,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Keep technical detail visible since it's needed for support, but lead with a friendly summary.
        print(f"[DJ Booth] Heads up: some system packages didn't install. The booth may still work — details: {result.stderr}")
    else:
        print("[DJ Booth] Audio tools installed.")

    print("[DJ Booth] Step 2/3: installing Python helpers (track analysis, metadata)")
    py_packages = [
        "mutagen>=1.47", "requests>=2.31",
        "aubio>=0.4.9", "numpy>=1.24", "scipy>=1.11",
    ]
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet"] + py_packages,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[DJ Booth] Heads up: some Python packages didn't install — details: {result.stderr}")
    else:
        print("[DJ Booth] Python helpers installed.")

    # pyaudio install can fail without portaudio — isolate so other packages don't roll back.
    print("[DJ Booth] Step 3/3: setting up microphone support (optional)")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "pyaudio>=0.2.14"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Non-fatal — mic input is optional and the rest of the booth works fine without it.
        print(f"[DJ Booth] Microphone support skipped (the rest of the booth works fine without it).")
    else:
        print("[DJ Booth] Microphone support ready.")

    music_dir = "/a0/usr/workdir/music"
    os.makedirs(music_dir, exist_ok=True)
    print(f"[DJ Booth] Your music folder is ready at: {music_dir}")
    print("[DJ Booth] All set! Open the DJ Booth from the sidebar and click Start.")


def uninstall():
    # Surfaces in the Plugin Install log on uninstall.
    print("[DJ Booth] Stopping the stream and cleaning up...")
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
        print(f"[DJ Booth] Heads up during shutdown: {e}")
    print("[DJ Booth] DJ Booth removed.")
