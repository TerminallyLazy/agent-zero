"""POST /api/plugins/jcode_harness/login_provider.

Body: ``{provider: "claude" | "openai" | ...}``.
Returns ``{auth_url, user_code?}`` for the OAuth/device flow.

Spike 0.8 verified ``--print-auth-url --json --no-browser`` flags so the
harness can render the auth URL inside A0's WebUI without opening a system
browser.
"""

from __future__ import annotations

import json
import subprocess

from helpers.api import ApiHandler, Request

from usr.plugins.jcode_harness.helpers.daemon import locate_jcode_binary


class LoginProvider(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        provider = (input or {}).get("provider")
        if not provider:
            return {"ok": False, "error": "provider required"}
        bin_path = locate_jcode_binary()
        if not bin_path:
            return {"ok": False, "error": "jcode not installed"}
        try:
            out = subprocess.check_output(
                [
                    bin_path,
                    "login",
                    "--provider",
                    provider,
                    "--print-auth-url",
                    "--json",
                    "--no-browser",
                ],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=30,
            )
            data = json.loads(out)
            return {
                "ok": True,
                "auth_url": data.get("auth_url"),
                "user_code": data.get("user_code"),
            }
        except subprocess.CalledProcessError as e:
            return {"ok": False, "error": (e.output or "")[:500]}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "login timed out"}
        except (json.JSONDecodeError, OSError) as e:
            return {"ok": False, "error": str(e)}
