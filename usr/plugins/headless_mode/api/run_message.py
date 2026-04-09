"""Run message API handler — fires a headless single-shot run."""
from __future__ import annotations

import json

from helpers.api import ApiHandler, Request

from usr.plugins.headless_mode.helpers.subprocess_run import run_cli_subprocess

_DEFAULT_TIMEOUT = 120
_MAX_TIMEOUT = 300


class RunMessage(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        message = str(input.get("message", "") or "").strip()
        if not message:
            return {"ok": False, "response": "", "context_id": "", "error": "Message is required"}

        ephemeral = bool(input.get("ephemeral", True))
        context_id = str(input.get("context_id", "") or "").strip()
        timeout = min(int(input.get("timeout", _DEFAULT_TIMEOUT) or _DEFAULT_TIMEOUT), _MAX_TIMEOUT)

        cmd_args = ["--message", message, "--output-format", "json"]
        if ephemeral:
            cmd_args.append("--ephemeral")
        if context_id:
            cmd_args.extend(["--context", context_id])

        ok, stdout, stderr = await run_cli_subprocess(cmd_args, timeout=timeout)

        if not ok:
            return {"ok": False, "response": "", "context_id": "", "error": stderr}

        try:
            data = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            return {
                "ok": False,
                "response": stdout,
                "context_id": "",
                "error": "Failed to parse CLI output as JSON",
            }

        return {
            "ok": True,
            "response": data.get("response", ""),
            "context_id": data.get("context", ""),
            "error": None,
        }
