"""Uninstall a user-installed plugin."""

from python.helpers.api import ApiHandler, Input, Output, Request, Response
from plugins.marketplace.helpers.git_ops import remove_plugin


class MarketplaceUninstall(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        plugin_id = input.get("plugin_id", "")
        if not plugin_id:
            return Response(status=400, response="Missing plugin_id")

        result = remove_plugin(plugin_id)

        if result.get("ok"):
            return {"ok": True, "message": f"Plugin '{plugin_id}' uninstalled."}
        else:
            return Response(status=400, response=result.get("error", "Uninstall failed."))
