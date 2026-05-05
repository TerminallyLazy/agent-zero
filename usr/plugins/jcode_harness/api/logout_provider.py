"""POST /api/plugins/jcode_harness/logout_provider.

Body: ``{provider: str}``.
Disconnects a provider by deleting its native jcode auth file.
"""

from __future__ import annotations

from pathlib import Path

from helpers.api import ApiHandler, Request

# We only delete jcode's native auth files, not cross-harness imports.
_AUTH_FILES = {
    "claude": ["~/.jcode/auth.json"],
    "openai": ["~/.jcode/openai-auth.json"],
    "gemini": ["~/.jcode/gemini_oauth.json"],
    "copilot": [], # copilot is managed by github CLI, jcode reads it
    "antigravity": ["~/.jcode/antigravity_oauth.json"],
    "azure": ["~/.jcode/azure_oauth.json"],
}

class LogoutProvider(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        provider = (input or {}).get("provider")
        if not provider:
            return {"ok": False, "error": "provider required"}
            
        files = _AUTH_FILES.get(provider)
        if files is None:
            return {"ok": False, "error": f"Unknown provider {provider}"}
            
        if not files:
            return {
                "ok": False, 
                "error": f"{provider} credentials are managed externally and cannot be deleted from here."
            }
            
        deleted = False
        for path_str in files:
            path = Path(path_str).expanduser()
            try:
                if path.exists():
                    path.unlink()
                    deleted = True
            except OSError as e:
                return {"ok": False, "error": str(e)}
                
        return {"ok": True, "deleted": deleted}
