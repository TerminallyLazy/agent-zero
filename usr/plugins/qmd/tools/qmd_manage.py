# usr/plugins/qmd/tools/qmd_manage.py
"""Tool: manage QMD collections and index. Requires management access."""
from __future__ import annotations

from helpers.tool import Tool, Response
from usr.plugins.qmd.helpers.client_access import get_or_create_client, is_management_enabled

_VALID_ACTIONS = {
    "collection_add", "collection_remove",
    "context_add", "context_remove",
    "update", "embed",
}


class QMDManage(Tool):

    async def execute(self, **kwargs) -> Response:
        # Gate check first
        if not is_management_enabled(self.agent):
            return Response(
                message="Management operations are disabled. Enable in plugin settings.",
                break_loop=False,
            )

        action = self.args.get("action", "")
        if action not in _VALID_ACTIONS:
            return Response(
                message=f"qmd_manage: invalid action '{action}'. Valid: {', '.join(sorted(_VALID_ACTIONS))}",
                break_loop=False,
            )

        # Build params for bridge call
        params: dict = {"_management_enabled": True}

        if action == "collection_add":
            params["path"] = self.args.get("path", "")
            params["name"] = self.args.get("name", "")
            if self.args.get("mask"):
                params["pattern"] = self.args["mask"]

        elif action == "collection_remove":
            params["name"] = self.args.get("name", "")

        elif action == "context_add":
            params["collection"] = self.args.get("collection", "")
            params["path"] = self.args.get("path", "")
            params["context"] = self.args.get("text", "")

        elif action == "context_remove":
            params["collection"] = self.args.get("collection", "")
            params["path"] = self.args.get("path", "")

        elif action == "update":
            if self.args.get("collections"):
                params["collections"] = self.args["collections"]
            if self.args.get("pull") is not None:
                params["pull"] = bool(self.args["pull"])

        elif action == "embed":
            if self.args.get("force") is not None:
                params["force"] = bool(self.args["force"])

        try:
            client = await get_or_create_client(self.agent)
            result = await client.call(action, params, gated=True, management_enabled=True)

            if "error" in result:
                return Response(message=f"QMD error: {result['error']}", break_loop=False)

            return Response(
                message=f"QMD {action}: {result.get('message', 'OK')}",
                break_loop=False,
            )

        except Exception as exc:
            return Response(message=f"QMD bridge error: {exc}", break_loop=False)
