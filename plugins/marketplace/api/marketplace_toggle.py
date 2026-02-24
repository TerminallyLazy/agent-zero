"""Activate or deactivate a plugin."""

import os
from python.helpers.api import ApiHandler, Input, Output, Request, Response
from python.helpers import files, plugins


class MarketplaceToggle(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        plugin_id = input.get("plugin_id", "")
        enabled = input.get("enabled", True)

        if not plugin_id:
            return Response(status=400, response="Missing plugin_id")

        plugin_dir = plugins.find_plugin_dir(plugin_id)
        if not plugin_dir:
            return Response(status=404, response=f"Plugin '{plugin_id}' not found.")

        usr_plugin_dir = files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR, plugin_id)
        os.makedirs(usr_plugin_dir, exist_ok=True)

        disabled_path = os.path.join(usr_plugin_dir, plugins.DISABLED_FILE_NAME)
        enabled_path = os.path.join(usr_plugin_dir, plugins.ENABLED_FILE_NAME)

        if enabled:
            if os.path.exists(disabled_path):
                os.remove(disabled_path)
            with open(enabled_path, "w") as f:
                f.write("")
        else:
            if os.path.exists(enabled_path):
                os.remove(enabled_path)
            with open(disabled_path, "w") as f:
                f.write("")

        status = "active" if enabled else "inactive"
        return {"ok": True, "status": status}
