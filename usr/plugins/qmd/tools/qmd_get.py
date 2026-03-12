# usr/plugins/qmd/tools/qmd_get.py
"""Tool: retrieve document content from the QMD index."""
from __future__ import annotations

from helpers.tool import Tool, Response
from usr.plugins.qmd.helpers.client_access import get_or_create_client


class QMDGet(Tool):

    async def execute(self, **kwargs) -> Response:
        path = self.args.get("path")          # file path or #docid
        pattern = self.args.get("pattern")    # glob or comma-separated list
        full = bool(self.args.get("full", False))
        line_numbers = bool(self.args.get("line_numbers", False))
        from_line = self.args.get("from_line")
        max_lines = int(self.args.get("max_lines", 200))
        max_bytes = int(self.args.get("max_bytes", 10240))

        if not path and not pattern:
            return Response(
                message="qmd_get: provide 'path' (single doc) or 'pattern' (multi-get).",
                break_loop=False,
            )

        try:
            client = await get_or_create_client(self.agent)

            if path:
                # Single document get
                params: dict = {"path": path, "full": full, "lineNumbers": line_numbers}
                if from_line is not None:
                    params["fromLine"] = int(from_line)
                if max_lines is not None:
                    params["maxLines"] = max_lines
                result = await client.call("get", params)
            else:
                # Multi-get by pattern
                params = {"pattern": pattern, "maxBytes": max_bytes}
                result = await client.call("multi_get", params)

            if "error" in result:
                return Response(message=f"QMD error: {result['error']}", break_loop=False)

            # Format response
            if path:
                doc = result.get("doc", {})
                content = doc.get("content", "") if isinstance(doc, dict) else ""
                doc_path = doc.get("path", path) if isinstance(doc, dict) else path
                return Response(
                    message=f"**{doc_path}**\n\n{content}",
                    break_loop=False,
                )
            else:
                # multi_get returns a list of documents
                docs = result.get("docs", result.get("items", []))
                if not docs:
                    return Response(message="No documents found.", break_loop=False)
                parts = []
                for doc in docs:
                    doc_path = doc.get("path", "?")
                    content = doc.get("content", "")
                    parts.append(f"**{doc_path}**\n\n{content}")
                return Response(message="\n\n---\n\n".join(parts), break_loop=False)

        except Exception as exc:
            return Response(message=f"QMD bridge error: {exc}", break_loop=False)
