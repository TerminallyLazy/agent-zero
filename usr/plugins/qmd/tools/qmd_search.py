# usr/plugins/qmd/tools/qmd_search.py
"""Tool: search indexed collections using QMD hybrid search."""
from __future__ import annotations

from helpers.tool import Tool, Response
from usr.plugins.qmd.helpers.client_access import get_or_create_client


class QMDSearch(Tool):

    async def execute(self, **kwargs) -> Response:
        mode = self.args.get("mode", "query")
        q = self.args.get("q", "")
        collections = self.args.get("collections")  # list or None
        limit = int(self.args.get("limit", 5))
        min_score = float(self.args.get("min_score", 0.0))
        intent = self.args.get("intent")
        explain = bool(self.args.get("explain", False))

        if not q:
            return Response(message="qmd_search: 'q' parameter is required.", break_loop=False)

        limit = min(limit, 10)

        # Map mode to bridge method
        method = mode if mode in ("query", "search", "vsearch") else "query"

        params: dict = {"query": q, "limit": limit, "minScore": min_score}
        if collections:
            params["collections"] = collections if isinstance(collections, list) else [collections]
        if intent:
            params["intent"] = intent
        if explain:
            params["explain"] = True

        try:
            client = await get_or_create_client(self.agent)
            result = await client.call(method, params)

            if "error" in result:
                return Response(message=f"QMD error: {result['error']}", break_loop=False)

            items = result.get("results", [])
            if not items:
                return Response(message="No results found.", break_loop=False)

            warning = result.get("warning", "")
            header = f"**QMD Search Results** (mode={method}, {len(items)} results)"
            if warning:
                header += f"\n⚠ {warning}"
            lines = [header + "\n"]
            for i, item in enumerate(items, 1):
                title = item.get("title") or item.get("displayPath") or item.get("path", "unknown")
                path = item.get("displayPath") or item.get("path", "")
                docid = item.get("docid") or item.get("id", "")
                score = item.get("score", 0.0)
                snippet = item.get("bestChunk") or item.get("snippet") or item.get("body") or item.get("content", "")
                if snippet and len(snippet) > 500:
                    snippet = snippet[:500] + "…"

                lines.append(f"**{i}. {title}**")
                if path:
                    lines.append(f"   Path: {path}")
                if docid:
                    lines.append(f"   ID: #{docid}")
                lines.append(f"   Score: {score:.0%}")
                if snippet:
                    lines.append(f"   Snippet: {snippet}")
                lines.append("")

            return Response(message="\n".join(lines), break_loop=False)

        except Exception as exc:
            return Response(
                message=f"QMD bridge error: {exc}",
                break_loop=False,
            )
