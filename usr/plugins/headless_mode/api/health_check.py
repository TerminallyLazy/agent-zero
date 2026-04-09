"""Health check API handler — runs CLI help + ephemeral test message."""
from __future__ import annotations

from datetime import datetime, timezone

from helpers import plugins
from helpers.api import ApiHandler, Request

from usr.plugins.headless_mode.helpers.subprocess_run import run_cli_subprocess

_TIMEOUT = 60
_PLUGIN = "headless_mode"


class HealthCheck(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        # Step 1: CLI help check
        cli_ok, cli_stdout, cli_stderr = await run_cli_subprocess(
            ["--help"], timeout=_TIMEOUT
        )
        if not cli_ok:
            result = {
                "ok": False,
                "cli_help_ok": False,
                "ephemeral_ok": False,
                "details": f"CLI help failed: {cli_stderr}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            _persist(result)
            return result

        # Step 2: Ephemeral test message
        eph_ok, eph_stdout, eph_stderr = await run_cli_subprocess(
            ["--message", "ping", "--ephemeral", "--output-format", "json"],
            timeout=_TIMEOUT,
        )

        ok = cli_ok and eph_ok
        if ok:
            details = "CLI loadable, ephemeral run succeeded"
        else:
            details = f"Ephemeral run failed: {eph_stderr}"

        result = {
            "ok": ok,
            "cli_help_ok": cli_ok,
            "ephemeral_ok": eph_ok,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _persist(result)
        return result


def _persist(result: dict) -> None:
    cfg = plugins.get_plugin_config(_PLUGIN) or {}
    cfg["last_health_check"] = result
    plugins.save_plugin_config(_PLUGIN, "", "", cfg)
