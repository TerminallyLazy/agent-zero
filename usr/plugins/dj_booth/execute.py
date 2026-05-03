"""User-triggered start. Runs on click in the Plugins UI.

A0 launches this as a subprocess with cwd = plugin dir, so the repo root
is NOT on sys.path by default. We prepend it before any cross-tree imports.

A0 also does NOT auto-run hooks.py:install(), so we bootstrap dependencies
on first Execute via helpers.setup.ensure_dependencies(). This is idempotent —
a no-op when icecast2/liquidsoap/ffmpeg etc. are already installed.
"""
import asyncio
import os
import sys

# Repo root = three levels up from this file (usr/plugins/dj_booth/execute.py)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main():
    print("[DJ Booth] Starting up...")
    try:
        # Bootstrap system + python deps if missing (first run only)
        from usr.plugins.dj_booth.helpers.setup import ensure_dependencies
        dep_status = ensure_dependencies(verbose=True)
        if not dep_status["ok"]:
            if dep_status.get("needs_manual_install"):
                print("[DJ Booth] ")
                print("[DJ Booth] Setup needs help from someone with admin access on this machine.")
                print(f"[DJ Booth] Missing: {', '.join(dep_status['missing_binaries'] + dep_status['missing_python'])}")
                print("[DJ Booth] If you're using the A0 desktop installer, check that you're running the latest version.")
                print("[DJ Booth] Otherwise ask whoever set up Agent Zero to install the listed packages.")
                return 1
            # If not flagged for manual install but still not ok, try to continue anyway
            print("[DJ Booth] Setup partially complete — attempting to start the stream anyway.")

        from helpers import plugins as plugins_helper
        from usr.plugins.dj_booth.helpers.lifecycle import start_stack
        from usr.plugins.dj_booth.api.dj_control import _get_library
        from usr.plugins.dj_booth.helpers.state import get_state

        cfg = plugins_helper.get_plugin_config("dj_booth") or {}
        if not cfg:
            print("[DJ Booth] Using default config (no custom settings yet — adjust in Settings → DJ Booth).")

        music_dir = cfg.get("music_dir", "/a0/usr/workdir/music")
        os.makedirs(music_dir, exist_ok=True)

        lib = _get_library()
        scanned = lib.scan(music_dir)
        get_state().library_count = scanned
        print(f"[DJ Booth] Music library: {scanned} tracks in {music_dir}")
        if scanned == 0:
            print(f"[DJ Booth] (No music yet — copy audio files into {music_dir}, then click Scan in the DJ Booth.)")

        asyncio.run(start_stack(cfg))

        port = cfg.get("icecast_port", 8000)
        mount = cfg.get("mount", "/stream")
        print(f"[DJ Booth] Stream is LIVE at http://localhost:{port}{mount}")
        print("[DJ Booth] Open the DJ Booth from the sidebar (🎧 button) to control playback.")
        print("[DJ Booth] Listeners can tune in by opening that URL in any browser, VLC, or Winamp.")
        return 0
    except Exception as e:
        import traceback
        print(f"[DJ Booth] ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
