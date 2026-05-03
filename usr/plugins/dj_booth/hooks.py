"""Plugin install/uninstall hooks for dj_booth.

A0 only auto-calls uninstall() — install() is a manual-install hook that
isn't reliably triggered by the plugin install flow. The actual dependency
bootstrap happens on first Execute via helpers.setup.ensure_dependencies(),
which this hook also delegates to so install can be invoked manually if
the framework ever wires it up.

Every print() appears in the Plugin Install / Execute log surfaced by the UI.
"""
import os
import sys

# Make sure repo root is on sys.path so 'from usr.plugins.dj_booth...' works
# when the framework calls these hooks via call_plugin_hook.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def install():
    """Optional manual install hook. Bootstraps deps via the shared setup helper."""
    print("[DJ Booth] Installing dependencies...")
    from usr.plugins.dj_booth.helpers.setup import ensure_dependencies
    status = ensure_dependencies(verbose=True)
    if status["ok"]:
        print("[DJ Booth] All set! Open the DJ Booth from the sidebar and click Start.")
    else:
        print("[DJ Booth] Install incomplete — see messages above. Try clicking Execute later, or contact your administrator.")


def uninstall():
    """Auto-called by A0 on plugin uninstall — stops services + cleanup."""
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
