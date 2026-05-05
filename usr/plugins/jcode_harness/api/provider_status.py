"""GET/POST /api/plugins/jcode_harness/provider_status

Reports which providers are connected (have credentials available).

Probes are filesystem + environment, matching DaemonSupervisor._has_creds
but resolved per-provider:
  - jcode native OAuth files (e.g. ~/.jcode/auth.json for Claude)
  - cross-harness creds (~/.config/github-copilot/, etc.)
  - canonical env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)

Returns {"providers": {<provider_id>: {"connected": bool, "source": str}}}
where ``source`` is "auth_file" | "env_var" | "" so the UI can explain
why a provider is connected.
"""

from __future__ import annotations

import os
from pathlib import Path

from helpers.api import ApiHandler, Request


# Canonical credential locations per provider. Keep in sync with
# DaemonSupervisor._has_creds and spec §5.3.
_PROVIDER_CREDS: dict[str, dict[str, list[str]]] = {
    "claude": {
        "auth_files": [
            "~/.jcode/auth.json",
            "~/.claude/.credentials.json",
        ],
        "env_vars": ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"],
    },
    "openai": {
        "auth_files": [
            "~/.jcode/openai-auth.json",
            "~/.codex/auth.json",
            "~/.local/share/opencode/auth.json",
        ],
        "env_vars": ["OPENAI_API_KEY"],
    },
    "gemini": {
        "auth_files": [
            "~/.jcode/gemini_oauth.json",
            "~/.gemini/oauth_creds.json",
        ],
        "env_vars": ["GEMINI_API_KEY"],
    },
    "copilot": {
        "auth_files": [
            "~/.config/github-copilot/hosts.json",
            "~/.config/github-copilot/apps.json",
            "~/.copilot/config.json",
        ],
        "env_vars": ["GITHUB_TOKEN", "GITHUB_COPILOT_TOKEN"],
    },
}


def _probe_provider(spec: dict) -> tuple[bool, str]:
    """Return (connected, source) where source is the location proving it."""
    for path_str in spec.get("auth_files", []):
        path = Path(path_str).expanduser()
        try:
            if path.is_file():
                return True, "auth_file"
        except OSError:
            continue
    for env_name in spec.get("env_vars", []):
        if os.environ.get(env_name):
            return True, "env_var"
    return False, ""


class ProviderStatus(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict:
        out: dict[str, dict] = {}
        for pid, spec in _PROVIDER_CREDS.items():
            connected, source = _probe_provider(spec)
            out[pid] = {"connected": connected, "source": source}
        return {"providers": out}
