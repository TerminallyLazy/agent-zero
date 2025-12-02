"""
Eden API - Clusters Endpoint

GET /eden/clusters - Fetch all smart clusters with tasks
GET /eden/clusters/:id - Fetch single cluster detail
"""

from datetime import datetime
from typing import Optional
import uuid

# Import Agent Zero API handler base
try:
    from python.helpers.api import ApiHandler
except ImportError:
    # Fallback for standalone testing
    class ApiHandler:
        @classmethod
        def requires_auth(cls) -> bool:
            return True

from python.helpers.eden.models import (
    Cluster,
    EdenTask,
    Patient,
    TaskCategory,
    TaskStatus,
    ConfidenceFactor,
)
from python.helpers.eden.clustering import ClusteringService


class ClustersHandler(ApiHandler):
    """
    Handle cluster-related API requests.

    GET /eden/clusters - List all clusters
    GET /eden/clusters/:id - Get single cluster
    """

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request) -> dict:
        """Process cluster requests."""
        method = request.method
        cluster_id = input.get("id")

        if method == "GET":
            if cluster_id:
                return await self._get_cluster(cluster_id)
            else:
                return await self._list_clusters(input)

        return {"error": "Method not allowed"}, 405

    async def _list_clusters(self, input: dict) -> dict:
        """List all clusters with optional filtering."""
        # Get clustering service
        service = ClusteringService.get_instance()

        # Get filter params
        status_filter = input.get("status")
        category_filter = input.get("category")
        needs_attention = input.get("needs_attention", False)

        # Get clusters
        clusters = await service.get_clusters()

        # Apply filters
        if needs_attention:
            clusters = [c for c in clusters if c.needs_attention]

        if status_filter:
            status = TaskStatus(status_filter)
            clusters = [
                c for c in clusters
                if any(t.status == status for t in c.tasks)
            ]

        if category_filter:
            category = TaskCategory(category_filter)
            clusters = [
                c for c in clusters
                if any(t.category == category for t in c.tasks)
            ]

        # Sort by priority (lower = higher priority)
        clusters.sort(key=lambda c: c.priority)

        return {
            "clusters": [c.to_dict() for c in clusters],
            "count": len(clusters),
        }

    async def _get_cluster(self, cluster_id: str) -> dict:
        """Get single cluster by ID."""
        service = ClusteringService.get_instance()
        cluster = await service.get_cluster(cluster_id)

        if not cluster:
            return {"error": "Cluster not found"}, 404

        return {"cluster": cluster.to_dict()}


# Handler for /eden/clusters endpoint
Clusters = ClustersHandler
