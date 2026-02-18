"""
EdgeQuake tool for Agent Zero.

Single tool with method-based routing for knowledge graph operations:
query, upload, list_documents, search_entities, graph_stats, health.
"""

import asyncio

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
                return await self._query(**kwargs)
            elif method == "upload":
                return await self._upload(**kwargs)
            elif method == "list_documents":
                return await self._list_documents(**kwargs)
            elif method == "search_entities":
                return await self._search_entities(**kwargs)
            elif method == "graph_stats":
                return await self._graph_stats(**kwargs)
            elif method == "health":
                return await self._health(**kwargs)
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

    def _get_client(self):
        """Get EdgeQuake client, returning (client, error_response) tuple."""
        from plugins.edgequake.helpers.edgequake_client import get_edgequake_client

        client = get_edgequake_client()
        if client is None:
            return None, Response(
                message="EdgeQuake is not configured. The user needs to set it up via the EdgeQuake button in the sidebar (hub icon) with a server URL and API key.",
                break_loop=False,
            )
        return client, None

    async def _query(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        query = str(kwargs.get("query") or self.args.get("query") or "").strip()
        if not query:
            return Response(message="Error: 'query' is required.", break_loop=False)

        mode = str(kwargs.get("mode") or self.args.get("mode") or "hybrid").strip().lower()
        valid_modes = ("naive", "local", "global", "hybrid", "mix", "bypass")
        if mode not in valid_modes:
            mode = "hybrid"

        self.set_progress(f"Querying EdgeQuake ({mode} mode)...")

        try:
            result = await asyncio.to_thread(client.query.execute, query=query, mode=mode)
            answer = getattr(result, "answer", str(result))
            return Response(message=answer, break_loop=False)
        except Exception as e:
            return self._handle_sdk_error(e, "query")

    async def _upload(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        content = str(kwargs.get("content") or self.args.get("content") or "").strip()
        if not content:
            return Response(message="Error: 'content' is required.", break_loop=False)

        title = str(kwargs.get("title") or self.args.get("title") or "").strip() or None

        self.set_progress("Uploading document to EdgeQuake...")

        try:
            doc = await asyncio.to_thread(client.documents.upload, content=content, title=title)
            doc_id = getattr(doc, "document_id", "unknown")
            return Response(
                message=f"Document uploaded successfully.\nDocument ID: {doc_id}\nTitle: {title or '(untitled)'}\nThe document is now being processed for entity extraction.",
                break_loop=False,
            )
        except Exception as e:
            return self._handle_sdk_error(e, "upload")

    async def _list_documents(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        raw_page = kwargs.get("page") if kwargs.get("page") is not None else self.args.get("page")
        raw_limit = kwargs.get("limit") if kwargs.get("limit") is not None else self.args.get("limit")
        page = int(raw_page) if raw_page is not None else 1
        limit = int(raw_limit) if raw_limit is not None else 10

        self.set_progress("Listing EdgeQuake documents...")

        try:
            docs = await asyncio.to_thread(client.documents.list, page=page, limit=limit)
            items = getattr(docs, "items", docs) if not isinstance(docs, list) else docs
            if not items:
                return Response(message="No documents found.", break_loop=False)

            lines = [f"Documents (page {page}):"]
            for doc in items:
                doc_id = getattr(doc, "document_id", getattr(doc, "id", "?"))
                title = getattr(doc, "title", "Untitled")
                status = getattr(doc, "status", "unknown")
                lines.append(f"- [{status}] {title} (ID: {doc_id})")
            return Response(message="\n".join(lines), break_loop=False)
        except Exception as e:
            return self._handle_sdk_error(e, "list_documents")

    async def _search_entities(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        keyword = str(kwargs.get("keyword") or self.args.get("keyword") or "").strip()
        if not keyword:
            return Response(message="Error: 'keyword' is required.", break_loop=False)

        self.set_progress(f"Searching EdgeQuake entities for '{keyword}'...")

        try:
            results = await asyncio.to_thread(client.graph.search, keyword=keyword)
            items = getattr(results, "entities", results) if not isinstance(results, list) else results
            if not items:
                return Response(message=f"No entities found matching '{keyword}'.", break_loop=False)

            lines = [f"Entities matching '{keyword}':"]
            for entity in items:
                name = getattr(entity, "name", str(entity))
                etype = getattr(entity, "entity_type", "")
                desc = getattr(entity, "description", "")
                type_str = f" ({etype})" if etype else ""
                desc_str = f": {desc[:200]}" if desc else ""
                lines.append(f"- {name}{type_str}{desc_str}")
            return Response(message="\n".join(lines), break_loop=False)
        except Exception as e:
            return self._handle_sdk_error(e, "search_entities")

    async def _graph_stats(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        self.set_progress("Fetching EdgeQuake graph statistics...")

        try:
            graph = await asyncio.to_thread(client.graph.get)
            entity_count = getattr(graph, "entity_count", getattr(graph, "num_entities", "?"))
            rel_count = getattr(graph, "relationship_count", getattr(graph, "num_relationships", "?"))
            labels = getattr(graph, "labels", [])

            lines = [
                "Knowledge Graph Statistics:",
                f"- Entities: {entity_count}",
                f"- Relationships: {rel_count}",
            ]
            if labels:
                label_str = ", ".join(str(label) for label in labels[:20])
                lines.append(f"- Labels: {label_str}")
            return Response(message="\n".join(lines), break_loop=False)
        except Exception as e:
            return self._handle_sdk_error(e, "graph_stats")

    async def _health(self, **kwargs) -> Response:
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

    def _handle_sdk_error(self, error: Exception, operation: str) -> Response:
        """Convert SDK exceptions into helpful Response messages."""
        err_str = str(error).lower()
        if "connection" in err_str or "refused" in err_str:
            msg = "EdgeQuake server is unreachable. Check that the server is running and the URL is correct."
        elif "401" in err_str or "unauthorized" in err_str or "auth" in err_str:
            msg = "EdgeQuake authentication failed. The API key may be invalid."
        elif "timeout" in err_str:
            msg = "EdgeQuake request timed out. The server may be overloaded."
        else:
            msg = f"EdgeQuake {operation} error: {str(error)}"
        return Response(message=msg, break_loop=False)
