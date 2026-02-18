"""
API handler for EdgeQuake document operations.

Actions:
- list: Paginated document listing
- upload: Ingest text content into the knowledge graph
- delete: Remove a document by ID
"""

import asyncio

from flask import Request
from python.helpers.api import ApiHandler, Input, Output


class EdgequakeDocuments(ApiHandler):

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "list")

        if action == "list":
            return await self._list(input)
        elif action == "upload":
            return await self._upload(input)
        elif action == "delete":
            return await self._delete(input)
        else:
            return {"error": f"Unknown action: {action}"}

    def _get_client(self):
        from plugins.edgequake.helpers.edgequake_client import get_edgequake_client
        return get_edgequake_client()

    async def _list(self, input: dict) -> dict:
        client = self._get_client()
        if client is None:
            return {"error": "EdgeQuake is not configured"}

        page = int(input.get("page", 1))
        limit = int(input.get("limit", 10))

        try:
            docs = await asyncio.to_thread(client.documents.list, page=page, limit=limit)
            items = getattr(docs, "items", docs) if not isinstance(docs, list) else docs

            documents = []
            for doc in (items or []):
                documents.append({
                    "document_id": getattr(doc, "document_id", getattr(doc, "id", "?")),
                    "title": getattr(doc, "title", "Untitled"),
                    "status": getattr(doc, "status", "unknown"),
                    "created_at": str(getattr(doc, "created_at", "")),
                    "entity_count": getattr(doc, "entity_count", getattr(doc, "num_entities", 0)),
                })

            total = getattr(docs, "total", len(documents))
            return {
                "documents": documents,
                "page": page,
                "limit": limit,
                "total": total,
            }
        except Exception as e:
            return {"error": f"Failed to list documents: {str(e)}"}

    async def _upload(self, input: dict) -> dict:
        client = self._get_client()
        if client is None:
            return {"error": "EdgeQuake is not configured"}

        content = str(input.get("content", "")).strip()
        if not content:
            return {"error": "Content is required"}

        title = str(input.get("title", "")).strip() or None

        try:
            doc = await asyncio.to_thread(client.documents.upload, content=content, title=title)
            return {
                "success": True,
                "document_id": getattr(doc, "document_id", "unknown"),
                "title": title or "(untitled)",
            }
        except Exception as e:
            return {"error": f"Failed to upload document: {str(e)}"}

    async def _delete(self, input: dict) -> dict:
        client = self._get_client()
        if client is None:
            return {"error": "EdgeQuake is not configured"}

        document_id = str(input.get("document_id", "")).strip()
        if not document_id:
            return {"error": "document_id is required"}

        try:
            await asyncio.to_thread(client.documents.delete, document_id=document_id)
            return {"success": True}
        except Exception as e:
            return {"error": f"Failed to delete document: {str(e)}"}
