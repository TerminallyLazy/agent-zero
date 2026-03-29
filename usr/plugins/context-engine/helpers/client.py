"""Async HTTP client for Context Engine MCP services.

Wraps the Indexer (code search, symbol graph, context answer, indexing)
and Memory (store, find) MCP endpoints behind a single client class.
All methods return dicts parsed from JSON responses.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from python.helpers.print_style import PrintStyle


class ContextEngineClient:
    """Thin async wrapper around Context Engine MCP HTTP endpoints."""

    def __init__(self, config: dict):
        self.indexer_endpoint = config.get(
            "indexer_endpoint", "http://localhost:8003"
        )
        self.memory_endpoint = config.get(
            "memory_endpoint", "http://localhost:8002"
        )
        self.collection = config.get("collection_name", "codebase")
        self.timeout = aiohttp.ClientTimeout(
            total=config.get("connection_timeout", 10)
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_mcp(
        self,
        endpoint: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 ``tools/call`` request to an MCP HTTP endpoint.

        The MCP streamable-http transport may respond with either:
        - ``application/json`` — a direct JSON-RPC response body, or
        - ``text/event-stream`` — SSE frames (``event: message\\ndata: {json}``).
        This method handles both formats transparently.

        Args:
            timeout_seconds: Override the default connection timeout (seconds).
                             Use for long-running operations like indexing.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        timeout = (
            aiohttp.ClientTimeout(total=timeout_seconds)
            if timeout_seconds
            else self.timeout
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        return {"ok": False, "error": f"HTTP {resp.status}: {text}"}

                    body = await self._parse_response(resp)

                    if "error" in body:
                        err = body["error"]
                        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                        return {"ok": False, "error": msg}

                    result = body.get("result", body)
                    return self._unwrap_mcp_result(result)
        except asyncio.TimeoutError:
            PrintStyle.error(f"Context Engine timeout ({tool_name}): request exceeded {timeout.total}s")
            return {"ok": False, "error": f"Request timed out after {int(timeout.total)}s. Indexing large codebases can take several minutes — try increasing the connection timeout in settings."}
        except aiohttp.ClientError as exc:
            PrintStyle.error(f"Context Engine connection error ({tool_name}): {exc}")
            return {"ok": False, "error": f"Connection error: {exc}"}
        except Exception as exc:
            PrintStyle.error(f"Context Engine error ({tool_name}): {exc}")
            return {"ok": False, "error": f"Unexpected error: {exc}"}

    @staticmethod
    async def _parse_response(resp: aiohttp.ClientResponse) -> dict[str, Any]:
        """Parse either JSON or SSE response from MCP streamable-http."""
        content_type = resp.content_type or ""

        if "text/event-stream" in content_type:
            # SSE format: lines of "event: <type>\ndata: <json>\n\n"
            # We extract the last JSON-RPC message from the data lines.
            raw = await resp.text()
            last_data = None
            for line in raw.splitlines():
                if line.startswith("data: "):
                    last_data = line[6:]
            if last_data:
                return json.loads(last_data)
            return {"error": "Empty SSE response from MCP server"}

        # Default: plain JSON response
        return await resp.json()

    @staticmethod
    def _unwrap_mcp_result(result: Any) -> dict[str, Any]:
        """Unwrap MCP tool result content envelope.

        MCP tool results wrap content in a list of ``{type, text}`` items.
        Extract and parse the first text item as JSON.
        """
        if isinstance(result, dict) and "content" in result:
            for item in result["content"]:
                if item.get("type") == "text":
                    try:
                        return json.loads(item["text"])
                    except (json.JSONDecodeError, KeyError):
                        return {"ok": True, "text": item["text"]}
        return result

    # ------------------------------------------------------------------
    # Indexer service tools (port 8003)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 10,
        language: str | None = None,
        under: str | None = None,
        include_snippet: bool = True,
    ) -> dict[str, Any]:
        """Hybrid semantic + lexical code search (repo_search)."""
        args: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "collection": self.collection,
            "include_snippet": include_snippet,
        }
        if language:
            args["language"] = language
        if under:
            args["under"] = under
        return await self._call_mcp(self.indexer_endpoint, "repo_search", args)

    async def answer(self, question: str, limit: int = 5) -> dict[str, Any]:
        """Context-aware Q&A backed by code search (context_answer)."""
        return await self._call_mcp(
            self.indexer_endpoint,
            "context_answer",
            {"question": question, "limit": limit, "collection": self.collection},
        )

    async def symbol_graph(
        self,
        symbol: str,
        query_type: str = "callers",
        limit: int = 10,
    ) -> dict[str, Any]:
        """AST-backed symbol relationship queries."""
        return await self._call_mcp(
            self.indexer_endpoint,
            "symbol_graph",
            {
                "symbol": symbol,
                "query_type": query_type,
                "limit": limit,
                "collection": self.collection,
            },
        )

    async def index(self, subdir: str = "", collection: str | None = None, recreate: bool = False) -> dict[str, Any]:
        """Trigger indexing of the workspace or a subdirectory.

        Args:
            subdir: Relative path under /work to index ("" for full workspace).
            collection: Target Qdrant collection (defaults to configured collection).
            recreate: If True, drop and recreate the collection before indexing.
        """
        args: dict[str, Any] = {"collection": collection or self.collection}
        if subdir:
            args["subdir"] = subdir
            return await self._call_mcp(self.indexer_endpoint, "qdrant_index", args, timeout_seconds=300)
        if recreate:
            args["recreate"] = True
        return await self._call_mcp(self.indexer_endpoint, "qdrant_index_root", args, timeout_seconds=300)

    async def search_tests(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Find test files related to a query."""
        return await self._call_mcp(
            self.indexer_endpoint,
            "search_tests_for",
            {"query": query, "limit": limit, "collection": self.collection},
        )

    async def search_callers(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Heuristic text-based search for callers of a symbol."""
        return await self._call_mcp(
            self.indexer_endpoint,
            "search_callers_for",
            {"query": query, "limit": limit, "collection": self.collection},
        )

    # ------------------------------------------------------------------
    # Memory service tools (port 8002)
    # ------------------------------------------------------------------

    async def memory_store(
        self, information: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Store knowledge into the memory system."""
        args: dict[str, Any] = {
            "information": information,
            "collection": self.collection,
        }
        if metadata:
            args["metadata"] = metadata
        return await self._call_mcp(self.memory_endpoint, "memory_store", args)

    async def memory_find(
        self,
        query: str,
        limit: int = 5,
        kind: str | None = None,
        topic: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve stored memories by semantic similarity."""
        args: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "collection": self.collection,
        }
        if kind:
            args["kind"] = kind
        if topic:
            args["topic"] = topic
        return await self._call_mcp(self.memory_endpoint, "memory_find", args)

    # ------------------------------------------------------------------
    # Status / health
    # ------------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        """Check Qdrant collection status via the indexer."""
        return await self._call_mcp(
            self.indexer_endpoint,
            "qdrant_status",
            {"collection": self.collection},
        )
