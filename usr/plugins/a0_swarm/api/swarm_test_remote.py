from helpers.api import ApiHandler, Request
from usr.plugins.a0_swarm.helpers.remotes import RemoteEndpoint
from usr.plugins.a0_swarm.helpers import a2a_runner


class SwarmTestRemote(ApiHandler):
    async def process(self, input: dict, request: Request):
        data = input or {}
        label = str(data.get("label") or data.get("endpoint") or "").strip()
        base_url = str(data.get("base_url") or data.get("url") or "").strip()
        auth_token = str(data.get("auth_token") or "").strip()

        if not base_url:
            return {"ok": False, "error": "base_url is required", "checks": {}, "endpoint": label}

        remote = RemoteEndpoint(label=label or base_url, base_url=base_url, auth_token=auth_token)
        checks = {
            "agent_card": {"ok": False, "error": ""},
            "submit": {"ok": False, "error": "not run"},
            "continuation": {"ok": False, "error": "not run"},
            "cancel": {"ok": False, "error": "not run"},
        }

        try:
            conn = await a2a_runner.open_connection(remote)
            try:
                await conn.get_agent_card()
                checks["agent_card"] = {"ok": True, "error": ""}
            finally:
                await conn.close()
        except Exception as exc:
            checks["agent_card"] = {"ok": False, "error": str(exc)}
            return {"ok": False, "error": str(exc), "checks": checks, "endpoint": remote.label}

        return {"ok": True, "error": "", "checks": checks, "endpoint": remote.label}
