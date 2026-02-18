"""
API handler for EdgeQuake knowledge graph operations.

Actions:
- search: Search entities by keyword
- stats: Get graph overview statistics
- load_all: Load all entities with relationships (for initial graph display)
"""

import urllib.parse

from flask import Request
from python.helpers.api import ApiHandler, Input, Output


def _fetch_entity(api_request, label: str) -> dict:
    """Fetch a single entity with its relationships via the neighborhood endpoint."""
    encoded_name = urllib.parse.quote(label, safe="")
    detail = api_request("GET", f"/api/v1/graph/entities/{encoded_name}/neighborhood?depth=1")
    if "error" in detail:
        return {"name": label}

    nodes = detail.get("nodes", [])
    edges = detail.get("edges", [])
    primary = next((n for n in nodes if n.get("id") == label), None)

    ent = {
        "name": label,
        "entity_type": primary.get("entity_type", "") if primary else "",
        "description": primary.get("description", "") if primary else "",
    }
    if edges:
        ent["relationships"] = [
            {
                "source": e.get("source", ""),
                "relationship": e.get("relation_type", ""),
                "target": e.get("target", ""),
            }
            for e in edges
        ]
    return ent


def _fetch_all_entities(api_request, limit: int = 50) -> tuple[list[str], list[dict]]:
    """Fetch all entity labels and their neighborhood data.

    Returns (labels, entities) where entities includes relationships.
    """
    label_result = api_request("GET", "/api/v1/graph/labels/search?q=")
    if "error" in label_result:
        return [], []

    labels = label_result.get("labels", [])
    if not labels:
        return labels, []

    entities = [_fetch_entity(api_request, label) for label in labels[:limit]]
    return labels, entities


class EdgequakeGraph(ApiHandler):

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "stats")

        if action == "search":
            return self._search(input)
        elif action == "stats":
            return self._stats()
        elif action == "load_all":
            return self._load_all()
        else:
            return {"error": f"Unknown action: {action}"}

    def _search(self, input: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import api_request

        keyword = str(input.get("keyword", "")).strip()
        if not keyword:
            return {"error": "keyword is required"}

        encoded = urllib.parse.quote(keyword, safe="")
        label_result = api_request("GET", f"/api/v1/graph/labels/search?q={encoded}")
        if "error" in label_result:
            return label_result

        labels = label_result.get("labels", [])
        if not labels:
            return {"entities": []}

        entities = [_fetch_entity(api_request, label) for label in labels[:10]]
        return {"entities": entities}

    def _stats(self) -> dict:
        from plugins.edgequake.helpers.edgequake_client import api_request

        labels, entities = _fetch_all_entities(api_request)

        # Count unique relationships across all entities
        seen_rels = set()
        for ent in entities:
            for rel in ent.get("relationships", []):
                key = (rel.get("source", ""), rel.get("relationship", ""), rel.get("target", ""))
                seen_rels.add(key)

        return {
            "entity_count": len(labels),
            "relationship_count": len(seen_rels),
            "labels": labels,
        }

    def _load_all(self) -> dict:
        """Load all entities with their relationships for initial graph display."""
        from plugins.edgequake.helpers.edgequake_client import api_request

        _, entities = _fetch_all_entities(api_request)
        return {"entities": entities}
