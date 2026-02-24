"""Install a plugin from the registry."""

import httpx
from python.helpers.api import ApiHandler, Input, Output, Request, Response
from plugins.marketplace.helpers.git_ops import clone_plugin

STATS_REPORT_URL = "https://a0-marketplace-web.vercel.app/api/stats/install"


class MarketplaceInstall(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        plugin_id = input.get("plugin_id", "")
        repo_url = input.get("repo_url", "")
        plugin_path = input.get("plugin_path", ".")
        branch = input.get("branch", "")

        if not plugin_id or not repo_url:
            return Response(status=400, response="Missing plugin_id or repo_url")

        result = clone_plugin(repo_url, plugin_path, plugin_id, branch=branch)

        # Fire-and-forget stats report
        if result.get("ok") and STATS_REPORT_URL:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(STATS_REPORT_URL, json={"plugin_id": plugin_id})
            except:
                pass

        if result.get("ok"):
            return {"ok": True, "message": f"Plugin '{plugin_id}' installed successfully."}
        else:
            return {"ok": False, "error": result.get("error", "Installation failed.")}
