"""POST /api/plugins/jcode_harness/complete_login.

Body: ``{provider: str, callback_url?: str, auth_code?: str}``.
Second leg of an OAuth flow whose first leg printed an auth URL via
``api/login_provider``. Spike 0.8 verified the
``--callback-url`` / ``--auth-code`` / ``--complete`` flag set on jcode
v0.11.10.
"""

from __future__ import annotations

import json
import subprocess

from helpers.api import ApiHandler, Request

from usr.plugins.jcode_harness.helpers.daemon import locate_jcode_binary


class CompleteLogin(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        provider = (input or {}).get("provider")
        if not provider:
            return {"ok": False, "error": "provider required"}
        bin_path = locate_jcode_binary()
        if not bin_path:
            return {"ok": False, "error": "jcode not installed"}
        cmd = [bin_path, "login", "--provider", provider, "--json"]
        callback = (input or {}).get("callback_url")
        code = (input or {}).get("auth_code")
        if callback:
            cmd += ["--callback-url", callback]
        elif code:
            cmd += ["--auth-code", code]
        else:
            cmd += ["--complete"]
        try:
            out = subprocess.check_output(
                cmd, text=True, stderr=subprocess.STDOUT, timeout=60
            )
        except subprocess.CalledProcessError as e:
            return {"ok": False, "error": (e.output or "")[:500]}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "login timed out"}
        out = out.strip()
        if out.startswith("{"):
            try:
                return {"ok": True, **json.loads(out)}
            except json.JSONDecodeError:
                return {"ok": True, "stdout": out}
        return {"ok": True, "stdout": out}
