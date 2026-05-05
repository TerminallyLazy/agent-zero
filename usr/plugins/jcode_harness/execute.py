#!/usr/bin/env python
"""Manual setup / repair / cleanup, invoked from Plugin Settings UI or CLI.

Per AGENTS.plugins.md §2, ``execute.py`` is the user-triggered re-runnable
operations entry point: setup, post-install, maintenance, repair.

A0 calls it via ``subprocess.run([sys.executable, execute_script],
cwd=plugin_dir)`` (api/plugins.py:292), so the repo root is NOT on
``sys.path``; we prepend it so ``usr.plugins.jcode_harness…`` imports
resolve. Mirrors the convention in usr/plugins/dj_booth/execute.py.

**Default behaviour (no args):** SETUP / REPAIR.
  - Detects or downloads the jcode binary
  - Verifies SHA-256 of the release archive
  - Smoke-tests ``jcode --version``
  - Re-runs the provider importer (idempotent)
  - Persists install metadata
  - Equivalent to ``hooks.install()`` but invokable on demand. Use this
    when the plugin was installed manually (git clone, dev checkout) and
    A0 never called the install hook automatically.

**``--cleanup`` flag:** STOP DAEMON + REMOVE STATE.
  - Stops the daemon (graceful SIGTERM, fall back to SIGKILL)
  - Removes ``~/.amplihack/jcode/<instance-id>/`` (per-instance runtime)
  - Leaves ``~/.jcode/`` (binary, sessions, memory, providers) intact
  - Add ``--delete-user-data`` to also remove ``~/.jcode/``

Examples (from the plugin directory or repo root)::

    # Setup / repair the binary + providers
    python usr/plugins/jcode_harness/execute.py

    # Tear down per-instance runtime
    python usr/plugins/jcode_harness/execute.py --cleanup

    # Full uninstall: remove ALL jcode state
    python usr/plugins/jcode_harness/execute.py --cleanup --delete-user-data

Spec ref: §5.2.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# sys.path bootstrap. A0 invokes execute.py via
# `subprocess.run([sys.executable, execute_script])` (api/plugins.py:292), so:
#   1. Python sets sys.path[0] = this file's directory
#      (= usr/plugins/jcode_harness/), making the plugin's own `helpers/`
#      package (regular package with __init__.py) shadow the FRAMEWORK
#      `helpers/` namespace package at /a0/helpers/. Subsequent imports of
#      `helpers.notification` then fail because the plugin's helpers package
#      doesn't have a `notification` module.
#   2. The repo root isn't on sys.path at all, so `usr.plugins.*` imports
#      raise ModuleNotFoundError.
# Two fixes:
#   (a) prepend the repo root so `usr.plugins.jcode_harness.*` resolves;
#   (b) drop the script directory from sys.path so `import helpers` falls
#       through to the framework's namespace package.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# Remove every alias the script-launch path may have inserted: empty
# string, ".", and the absolute script directory all resolve to the
# same package-shadow.
for _alias in (_SCRIPT_DIR, "", "."):
    while _alias in sys.path:
        sys.path.remove(_alias)


def _stdout_reporter(level: str, msg: str) -> None:
    """Print setup progress to stdout — A0's plugin Execute UI displays this."""
    prefix = {
        "info": "  ",
        "success": "✓ ",
        "warning": "! ",
        "error": "✗ ",
    }.get(level, "  ")
    print(f"{prefix}{msg}", flush=True)


def setup() -> int:
    """Run setup / repair. Returns process exit code."""
    print("=== jcode_harness setup ===", flush=True)
    try:
        from usr.plugins.jcode_harness.hooks import run_setup
    except Exception as e:
        print(f"✗ Cannot import setup module: {e}", flush=True)
        return 1
    try:
        result = run_setup(report=_stdout_reporter)
    except Exception as e:
        print(f"✗ Setup failed: {e}", flush=True)
        return 1
    print("", flush=True)
    print(f"binary:  {result['binary_path']}", flush=True)
    print(f"version: {result['version']}", flush=True)
    if result.get("imported"):
        print(f"imported providers: {', '.join(result['imported'])}", flush=True)
    if result.get("skipped"):
        for pid, reason in result["skipped"].items():
            print(f"skipped {pid}: {reason}", flush=True)
    if result.get("self_dev_available"):
        print("self-dev: available (Rust toolchain present)", flush=True)
    else:
        print("self-dev: unavailable (install Rust to enable)", flush=True)
    print("", flush=True)
    print("Done. The daemon is lazy-spawned on first tool use.", flush=True)
    print("Open the jcode plugin from Plugins → jcode harness to log in.", flush=True)
    return 0


def cleanup(also_delete_user_data: bool = False) -> int:
    """Stop daemon, remove per-instance runtime dir. Returns exit code."""
    print("=== jcode_harness cleanup ===", flush=True)
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod
    from usr.plugins.jcode_harness.helpers import paths as paths_mod

    instance_dir = paths_mod.jcode_runtime_dir()
    bin_path = daemon_mod.locate_jcode_binary()
    if bin_path:
        sup = daemon_mod.DaemonSupervisor(bin_path, instance_dir)
        sup.stop()
        print("✓ daemon stopped", flush=True)
    else:
        print("  no jcode binary found; skipping daemon stop", flush=True)

    if instance_dir.exists():
        shutil.rmtree(instance_dir)
        print(f"✓ removed {instance_dir}", flush=True)
    else:
        print(f"  no per-instance dir at {instance_dir}", flush=True)

    if also_delete_user_data:
        user_data = Path.home() / ".jcode"
        if user_data.exists():
            shutil.rmtree(user_data)
            print(f"✓ removed {user_data} (binary, sessions, memory, providers)", flush=True)
        else:
            print(f"  no user data dir at {user_data}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch on argv. Default = setup; ``--cleanup`` = cleanup."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "--cleanup" in args:
        return cleanup(also_delete_user_data="--delete-user-data" in args)
    return setup()


if __name__ == "__main__":
    sys.exit(main())
