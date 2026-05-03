"""User-triggered first-time setup. Runs once when the user clicks Execute
in the Plugins UI.

What this does:
  1. Add repo root to sys.path so 'helpers.*' / 'usr.plugins.*' imports work
  2. Install system + Python deps (apt + pip) if missing
  3. Scan the music library
  4. Tell the user to open the DJ Booth and click Start

What this does NOT do:
  - Start the stream. Streaming services (HTTP server, encoder, health loop)
    must live inside A0's long-running Flask event loop, not in this short-lived
    subprocess. If they were started here, asyncio.run() would tear them down
    the moment this function returns. Instead, the Start button in the DJ
    Booth modal triggers /api/plugins/dj_booth/dj_control with action=start,
    which runs in Flask's persistent loop and keeps the stream alive.
"""
import os
import sys

# Repo root = three levels up from this file (usr/plugins/dj_booth/execute.py)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main():
    print("[DJ Booth] Setup starting...")
    try:
        from usr.plugins.dj_booth.helpers.setup import ensure_dependencies
        dep_status = ensure_dependencies(verbose=True)
        if not dep_status["ok"] and dep_status.get("needs_manual_install"):
            print("[DJ Booth] ")
            print("[DJ Booth] Setup needs help from someone with admin access on this machine.")
            print(f"[DJ Booth] Missing: {', '.join(dep_status['missing_binaries'] + dep_status['missing_python'])}")
            print("[DJ Booth] Click Execute again after they're installed.")
            return 1

        from helpers import plugins as plugins_helper
        from usr.plugins.dj_booth.api.dj_control import _get_library
        from usr.plugins.dj_booth.helpers.state import get_state

        cfg = plugins_helper.get_plugin_config("dj_booth") or {}
        if not cfg:
            print("[DJ Booth] Using default settings (you can change them in Settings → DJ Booth).")

        music_dir = cfg.get("music_dir", "/a0/usr/workdir/music")
        os.makedirs(music_dir, exist_ok=True)

        lib = _get_library()
        scanned = lib.scan(music_dir)
        get_state().library_count = scanned
        print(f"[DJ Booth] Music library: {scanned} tracks in {music_dir}")
        if scanned == 0:
            print(f"[DJ Booth] (No music yet — copy audio files into {music_dir}.)")
            print(f"[DJ Booth] You can add files later and click Scan in the DJ Booth.")

        print("[DJ Booth] ")
        print("[DJ Booth] ✓ Setup complete!")
        print("[DJ Booth] ")
        print("[DJ Booth] Next step:")
        print("[DJ Booth]   1. Click the radio icon (🎙) in the left sidebar to open the DJ Booth")
        print("[DJ Booth]   2. Click the green Start button at the top")
        print("[DJ Booth]   3. Click 'Share Online' to get a public link anyone can listen to")
        print("[DJ Booth] ")
        return 0
    except Exception as e:
        import traceback
        print(f"[DJ Booth] ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
