"""User-triggered start. Runs on click in the Plugins UI."""
import asyncio
import sys


def main():
    print("[dj_booth] starting DJ Booth services...")
    try:
        from helpers.plugins import get_plugin_config
        from usr.plugins.dj_booth.helpers.lifecycle import start_stack
        from usr.plugins.dj_booth.api.dj_control import _get_library
        from usr.plugins.dj_booth.helpers.state import get_state

        cfg = get_plugin_config("dj_booth") or {}

        lib = _get_library()
        scanned = lib.scan(cfg.get("music_dir", "/a0/usr/workdir/music"))
        get_state().library_count = scanned
        print(f"[dj_booth] library scanned: {scanned} tracks")

        asyncio.run(start_stack(cfg))

        port = cfg.get("icecast_port", 8000)
        mount = cfg.get("mount", "/stream")
        print(f"[dj_booth] stream live at http://localhost:{port}{mount}")
        print("[dj_booth] tune in with VLC, Winamp, or any ICY-compatible client.")
        return 0
    except Exception as e:
        print(f"[dj_booth] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
