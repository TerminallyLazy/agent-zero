# usr/plugins/qmd/tools/qmd_status.py
"""Tool: report QMD index status and available collections."""
from __future__ import annotations

from helpers.tool import Tool, Response
from usr.plugins.qmd.helpers.client_access import get_or_create_client


class QMDStatus(Tool):

    async def execute(self, **kwargs) -> Response:
        try:
            client = await get_or_create_client(self.agent)
            result = await client.call("status")

            if "error" in result:
                return Response(message=f"QMD error: {result['error']}", break_loop=False)

            lines = ["**QMD Index Status**\n"]

            collections = result.get("collections", [])
            if collections:
                lines.append(f"Collections ({len(collections)}):")
                for col in collections:
                    name = col.get("name", "?")
                    count = col.get("doc_count", 0)
                    lines.append(f"  • {name}: {count} documents")
            else:
                lines.append("No collections indexed.")

            return Response(message="\n".join(lines), break_loop=False)

        except Exception as exc:
            return Response(
                message=f"QMD bridge error: {exc}\nRun plugin initialization to set up the bridge.",
                break_loop=False,
            )
