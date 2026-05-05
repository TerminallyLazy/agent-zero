#!/usr/bin/env python
"""Manual cleanup invoked from plugin UI or CLI.

Per AGENTS.plugins.md §2, hooks.py only guarantees ``install()`` and
``pre_update()``. Cleanup lives here so it can be re-run after plugin
removal too.

Usage::

    python -m usr.plugins.jcode_harness.execute
        # remove ~/.amplihack/jcode/<instance-id>/

    python -m usr.plugins.jcode_harness.execute --delete-user-data
        # also remove ~/.jcode/

Spec ref: §5.2.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main(also_delete_user_data: bool = False) -> int:
    """Stop the daemon (if any) and remove plugin-managed directories.

    Returns ``0`` on success. Idempotent — missing directories are ignored.
    """
    # Imports inside main so the patch points used by tests
    # (``...helpers.daemon.locate_jcode_binary`` etc.) resolve against the
    # already-imported module objects, not stale locals captured at module
    # load time.
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod
    from usr.plugins.jcode_harness.helpers import paths as paths_mod

    instance_dir = paths_mod.jcode_runtime_dir()
    bin_path = daemon_mod.locate_jcode_binary()
    if bin_path:
        sup = daemon_mod.DaemonSupervisor(bin_path, instance_dir)
        sup.stop()
        print("daemon stopped")

    if instance_dir.exists():
        shutil.rmtree(instance_dir)
        print(f"removed {instance_dir}")

    if also_delete_user_data:
        user_data = Path.home() / ".jcode"
        if user_data.exists():
            shutil.rmtree(user_data)
            print(f"removed {user_data}")
    return 0


if __name__ == "__main__":
    sys.exit(main(also_delete_user_data="--delete-user-data" in sys.argv))
