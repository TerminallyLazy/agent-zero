"""User-triggered start. Runs on click in the Plugins UI.

Important: this script is launched by A0 as a subprocess with cwd = plugin dir,
so the repo root is NOT on sys.path by default. We prepend it before any
'helpers.*' or 'usr.plugins.*' imports.
"""
import asyncio
import os
import sys

# Repo root = three levels up from this file (usr/plugins/dj_booth/execute.py)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main():
    print("[dj_booth] Starting DJ Booth services...")
    try:
        from helpers import plugins as plugins_helper
        from usr.plugins.dj_booth.helpers.lifecycle import start_stack
        from usr.plugins.dj_booth.api.dj_control import _get_library
        from usr.plugins.dj_booth.helpers.state import get_state

        cfg = plugins_helper.get_plugin_config("dj_booth") or {}
        if not cfg:
            print("[dj_booth] WARNING: no config found — using defaults from default_config.yaml")

        music_dir = cfg.get("music_dir", "/a0/usr/workdir/music")
        os.makedirs(music_dir, exist_ok=True)

        lib = _get_library()
        scanned = lib.scan(music_dir)
        get_state().library_count = scanned
        print(f"[dj_booth] Music library scanned: {scanned} tracks in {music_dir}")
        if scanned == 0:
            print(f"[dj_booth] (Tip: copy music files into {music_dir}, then click Execute again or use the Scan button in the DJ Booth UI.)")

        asyncio.run(start_stack(cfg))

        port = cfg.get("icecast_port", 8000)
        mount = cfg.get("mount", "/stream")
        print(f"[dj_booth] Stream live at http://localhost:{port}{mount}")
        print("[dj_booth] Open the DJ Booth from the sidebar to control it.")
        print("[dj_booth] Listeners can tune in by opening that URL in any browser, VLC, or Winamp.")
        return 0
    except Exception as e:
        import traceback
        print(f"[dj_booth] ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
