"""
EdgeQuake tool for Agent Zero.

Single tool with method-based routing for knowledge graph operations:
query, upload, list_documents, search_entities, graph_stats, health.

Uses raw HTTP to the EdgeQuake REST API — no SDK dependency.
"""

from python.helpers.tool import Tool, Response


class EdgequakeTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (
            (kwargs.get("method") or self.args.get("method") or self.method or "")
            .strip()
            .lower()
        )

        try:
            if method == "query":
                return self._query(**kwargs)
            elif method == "upload":
                return self._upload(**kwargs)
            elif method == "list_documents":
                return self._list_documents(**kwargs)
            elif method == "search_entities":
                return self._search_entities(**kwargs)
            elif method == "graph_stats":
                return self._graph_stats(**kwargs)
            elif method == "health":
                return self._health(**kwargs)
            else:
                return Response(
                    message="Error: missing or invalid 'method'. Supported: query, upload, list_documents, search_entities, graph_stats, health.",
                    break_loop=False,
                )
        except Exception as e:
            return Response(
                message=f"EdgeQuake error: {str(e)}",
                break_loop=False,
            )

    def _api(self, method: str, path: str, body: dict | None = None) -> dict:
        from plugins.edgequake.helpers.edgequake_client import api_request
        return api_request(method, path, body)

    def _query(self, **kwargs) -> Response:
        query = str(kwargs.get("query") or self.args.get("query") or "").strip()
        if not query:
            return Response(message="Error: 'query' is required.", break_loop=False)

        mode = str(kwargs.get("mode") or self.args.get("mode") or "hybrid").strip().lower()
        valid_modes = ("naive", "local", "global", "hybrid", "mix", "bypass")
        if mode not in valid_modes:
            mode = "hybrid"

        self.set_progress(f"Querying EdgeQuake ({mode} mode)...")

        result = self._api("POST", "/api/v1/query", {"query": query, "mode": mode})
        if "error" in result:
            return Response(message=f"EdgeQuake query error: {result['error']}", break_loop=False)

        answer = result.get("response", result.get("answer", str(result)))
        return Response(message=answer, break_loop=False)

    def _upload(self, **kwargs) -> Response:
        content = str(kwargs.get("content") or self.args.get("content") or "").strip()
        if not content:
            return Response(message="Error: 'content' is required.", break_loop=False)

        title = str(kwargs.get("title") or self.args.get("title") or "").strip() or None

        self.set_progress("Uploading document to EdgeQuake...")

        body = {"content": content}
        if title:
            body["title"] = title

        result = self._api("POST", "/api/v1/documents", body)
        if "error" in result:
            return Response(message=f"EdgeQuake upload error: {result['error']}", break_loop=False)

        doc_id = result.get("document_id", result.get("id", "unknown"))
        return Response(
            message=f"Document uploaded successfully.\nDocument ID: {doc_id}\nTitle: {title or '(untitled)'}\nThe document is now being processed for entity extraction.",
            break_loop=False,
        )

    def _list_documents(self, **kwargs) -> Response:
        raw_page = kwargs.get("page") if kwargs.get("page") is not None else self.args.get("page")
        raw_limit = kwargs.get("limit") if kwargs.get("limit") is not None else self.args.get("limit")
        page = int(raw_page) if raw_page is not None else 1
        limit = int(raw_limit) if raw_limit is not None else 10

        self.set_progress("Listing EdgeQuake documents...")

        result = self._api("GET", f"/api/v1/documents?page={page}&page_size={limit}")
        if "error" in result:
            return Response(message=f"EdgeQuake error: {result['error']}", break_loop=False)

        items = result.get("documents", [])
        if not items:
            return Response(message="No documents found.", break_loop=False)

        lines = [f"Documents (page {page}):"]
        for doc in items:
            doc_id = doc.get("document_id", doc.get("id", "?"))
            title = doc.get("title", "Untitled")
            status = doc.get("status", "unknown")
            lines.append(f"- [{status}] {title} (ID: {doc_id})")
        return Response(message="\n".join(lines), break_loop=False)

    def _search_entities(self, **kwargs) -> Response:
        keyword = str(kwargs.get("keyword") or self.args.get("keyword") or "").strip()
        if not keyword:
            return Response(message="Error: 'keyword' is required.", break_loop=False)

        self.set_progress(f"Searching EdgeQuake entities for '{keyword}'...")

        # Step 1: Find matching entity labels
        import urllib.parse
        encoded = urllib.parse.quote(keyword, safe="")
        label_result = self._api("GET", f"/api/v1/graph/labels/search?q={encoded}")
        if "error" in label_result:
            return Response(message=f"EdgeQuake search error: {label_result['error']}", break_loop=False)

        labels = label_result.get("labels", [])
        if not labels:
            return Response(message=f"No entities found matching '{keyword}'.", break_loop=False)

        # Step 2: Get neighborhood for each matching entity (first 5)
        lines = [f"Entities matching '{keyword}':"]
        for label in labels[:5]:
            encoded_name = urllib.parse.quote(label, safe="")
            detail = self._api("GET", f"/api/v1/graph/entities/{encoded_name}/neighborhood?depth=1")
            if "error" in detail:
                lines.append(f"- {label}")
                continue

            nodes = detail.get("nodes", [])
            edges = detail.get("edges", [])
            # Find the primary entity node
            primary = next((n for n in nodes if n.get("id") == label), None)
            if primary:
                etype = primary.get("entity_type", "")
                desc = primary.get("description", "")
                type_str = f" ({etype})" if etype else ""
                desc_str = f": {desc[:200]}" if desc else ""
                lines.append(f"- {label}{type_str}{desc_str}")
            else:
                lines.append(f"- {label}")

            # Show relationships
            for edge in edges[:10]:
                src = edge.get("source", "")
                tgt = edge.get("target", "")
                rel = edge.get("relation_type", edge.get("relationship", ""))
                lines.append(f"  -> {src} --[{rel}]--> {tgt}")

        return Response(message="\n".join(lines), break_loop=False)

    def _graph_stats(self, **kwargs) -> Response:
        import urllib.parse

        self.set_progress("Fetching EdgeQuake graph statistics...")

        # Get all entity labels
        label_result = self._api("GET", "/api/v1/graph/labels/search?q=")
        labels = label_result.get("labels", []) if "error" not in label_result else []

        # Count relationships by sampling entity neighborhoods
        seen_rels = set()
        for label in labels[:50]:
            encoded = urllib.parse.quote(label, safe="")
            detail = self._api("GET", f"/api/v1/graph/entities/{encoded}/neighborhood?depth=1")
            if "error" not in detail:
                for edge in detail.get("edges", []):
                    key = (edge.get("source", ""), edge.get("relation_type", ""), edge.get("target", ""))
                    seen_rels.add(key)

        lines = [
            "Knowledge Graph Statistics:",
            f"- Entities: {len(labels)}",
            f"- Relationships: {len(seen_rels)}",
        ]
        return Response(message="\n".join(lines), break_loop=False)

    def _health(self, **kwargs) -> Response:
        from plugins.edgequake.helpers.edgequake_client import test_connection

        self.set_progress("Checking EdgeQuake health...")
        result = test_connection()

        if "error" in result:
            return Response(message=f"EdgeQuake health check failed: {result['error']}", break_loop=False)

        lines = [
            "EdgeQuake is healthy:",
            f"- Status: {result.get('status', '?')}",
            f"- Version: {result.get('version', '?')}",
            f"- Storage: {result.get('storage_mode', '?')}",
            f"- LLM Provider: {result.get('llm_provider_name', '?')}",
        ]
        return Response(message="\n".join(lines), break_loop=False)
