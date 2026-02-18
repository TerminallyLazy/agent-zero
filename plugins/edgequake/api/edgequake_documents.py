"""
API handler for EdgeQuake document operations.

Actions:
- list: Paginated document listing
- upload: Ingest text content into the knowledge graph
- delete: Remove a document by ID
"""

from flask import Request
from python.helpers.api import ApiHandler, Input, Output


class EdgequakeDocuments(ApiHandler):

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "list")

        if action == "list":
            return self._list(input)
        elif action == "upload":
            return self._upload(input)
        elif action == "delete":
            return self._delete(input)
        else:
            return {"error": f"Unknown action: {action}"}

    def _list(self, input: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import api_request

        page = int(input.get("page", 1))
        limit = int(input.get("limit", 10))

        result = api_request("GET", f"/api/v1/documents?page={page}&page_size={limit}")
        if "error" in result:
            return result

        documents = []
        for doc in result.get("documents", []):
            documents.append({
                "document_id": doc.get("document_id", doc.get("id", "?")),
                "title": doc.get("title", "Untitled"),
                "status": doc.get("status", "unknown"),
                "created_at": str(doc.get("created_at", "")),
                "entity_count": doc.get("entity_count", doc.get("num_entities", 0)),
            })

        return {
            "documents": documents,
            "page": page,
            "limit": limit,
            "total": result.get("total", len(documents)),
        }

    def _upload(self, input: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import api_request

        content = str(input.get("content", "")).strip()
        if not content:
            return {"error": "Content is required"}

        title = str(input.get("title", "")).strip() or None
        body = {"content": content}
        if title:
            body["title"] = title

        result = api_request("POST", "/api/v1/documents", body)
        if "error" in result:
            return result

        return {
            "success": True,
            "document_id": result.get("document_id", result.get("id", "unknown")),
            "title": title or "(untitled)",
        }

    def _delete(self, input: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import api_request

        document_id = str(input.get("document_id", "")).strip()
        if not document_id:
            return {"error": "document_id is required"}

        result = api_request("DELETE", f"/api/v1/documents/{document_id}")
        if "error" in result:
            return result

        return {"success": True}
