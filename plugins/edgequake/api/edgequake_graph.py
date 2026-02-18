"""
API handler for EdgeQuake knowledge graph operations.

Actions:
- search: Search entities by keyword
- stats: Get graph overview statistics
"""

import asyncio

from flask import Request
from python.helpers.api import ApiHandler, Input, Output


class EdgequakeGraph(ApiHandler):

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "stats")

        if action == "search":
            return await self._search(input)
        elif action == "stats":
            return await self._stats()
        else:
            return {"error": f"Unknown action: {action}"}

    def _get_client(self):
        from plugins.edgequake.helpers.edgequake_client import get_edgequake_client
        return get_edgequake_client()

    async def _search(self, input: dict) -> dict:
        client = self._get_client()
        if client is None:
            return {"error": "EdgeQuake is not configured"}

        keyword = str(input.get("keyword", "")).strip()
        if not keyword:
            return {"error": "keyword is required"}

        try:
            results = await asyncio.to_thread(client.graph.search, keyword=keyword)
            items = getattr(results, "entities", results) if not isinstance(results, list) else results

            entities = []
            for entity in (items or []):
                ent = {
                    "name": getattr(entity, "name", str(entity)),
                    "entity_type": getattr(entity, "entity_type", ""),
                    "description": getattr(entity, "description", ""),
                }
                # Include relationships if available
                rels = getattr(entity, "relationships", None)
                if rels:
                    ent["relationships"] = [
                        {
                            "source": getattr(r, "source", ""),
                            "relationship": getattr(r, "relationship", getattr(r, "type", "")),
                            "target": getattr(r, "target", ""),
                        }
                        for r in rels
                    ]
                entities.append(ent)

            return {"entities": entities}
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    async def _stats(self) -> dict:
        client = self._get_client()
        if client is None:
            return {"error": "EdgeQuake is not configured"}

        try:
            graph = await asyncio.to_thread(client.graph.get)
            return {
                "entity_count": getattr(graph, "entity_count", getattr(graph, "num_entities", 0)),
                "relationship_count": getattr(graph, "relationship_count", getattr(graph, "num_relationships", 0)),
                "labels": [str(label) for label in getattr(graph, "labels", [])][:50],
            }
        except Exception as e:
            return {"error": f"Failed to get graph stats: {str(e)}"}
