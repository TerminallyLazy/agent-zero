import os

from python.helpers.api import ApiHandler, Request, Response
from python.helpers import plugins, files


class Plugins(ApiHandler):
    """
    Core plugin management API.
    Actions: get_config, save_config
    """

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = input.get("action", "get_config")

        # Accept legacy aliases during migration.
        if action == "get_config":
            plugin_name = input.get("plugin_name", "")
            project_name = input.get("project_name", "")
            agent_profile = input.get("agent_profile", "")
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")

            result = plugins.find_plugin_assets(
                plugins.CONFIG_FILE_NAME,
                plugin_name=plugin_name,
                project_name=project_name,
                agent_profile=agent_profile,
                only_first=True,
            )
            if result:
                entry = result[0]
                path = entry.get("path", "")
                settings = files.read_file_json(path) if path else {}
                loaded_project_name = entry.get("project_name", "")
                loaded_agent_profile = entry.get("agent_profile", "")
            else:
                settings = plugins.get_plugin_config(plugin_name, agent=None) or {}
                default_path = files.get_abs_path(
                    plugins.find_plugin_dir(plugin_name), plugins.CONFIG_DEFAULT_FILE_NAME
                )
                path = default_path if files.exists(default_path) else ""
                loaded_project_name = ""
                loaded_agent_profile = ""

            return {
                "ok": True,
                "loaded_path": path,
                "loaded_project_name": loaded_project_name,
                "loaded_agent_profile": loaded_agent_profile,
                "data": settings,
            }

        if action == "list_configs":
            plugin_name = input.get("plugin_name", "")
            asset_type = input.get("asset_type", "config")
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")

            configs = plugins.find_plugin_assets(
                plugins.CONFIG_FILE_NAME if asset_type == "config" else plugins.TOGGLE_FILE_PATTERN,
                plugin_name=plugin_name,
                project_name="*",
                agent_profile="*",
                only_first=False,
            )

            return {"ok": True, "data": configs}

        if action == "delete_config":
            plugin_name = input.get("plugin_name", "")
            path = input.get("path", "")
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")
            if not path:
                return Response(status=400, response="Missing path")

            configs = plugins.find_plugin_assets(
                plugins.CONFIG_FILE_NAME,
                plugin_name=plugin_name,
                project_name="*",
                agent_profile="*",
                only_first=False,
            )
            allowed_paths = {c.get("path", "") for c in configs}
            if path not in allowed_paths:
                return Response(status=400, response="Invalid path")

            if not files.exists(path):
                return {"ok": True}

            try:
                os.remove(path)
            except Exception as e:
                return Response(status=500, response=f"Failed to delete config: {str(e)}")

            return {"ok": True}

        if action == "save_config":
            plugin_name = input.get("plugin_name", "")
            project_name = input.get("project_name", "")
            agent_profile = input.get("agent_profile", "")
            settings = input.get("settings", {})
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")
            if not isinstance(settings, dict):
                return Response(status=400, response="settings must be an object")
            plugins.save_plugin_config(plugin_name, project_name, agent_profile, settings)
            return {"ok": True}

        return Response(status=400, response=f"Unknown action: {action}")
