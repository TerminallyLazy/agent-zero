"""GET/POST /api/plugins/jcode_harness/daemon_status.

Returns the daemon health dict produced by ``DaemonSupervisor.health()``.
"""

from __future__ import annotations

from helpers.api import ApiHandler, Request


class DaemonStatus(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict:
        from usr.plugins.jcode_harness.helpers.daemon import (
            DaemonSupervisor,
            locate_jcode_binary,
        )
        from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir

        bin_path = locate_jcode_binary()
        if not bin_path:
            return {"running": False, "error": "binary not installed"}
        sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
        return sup.health()
