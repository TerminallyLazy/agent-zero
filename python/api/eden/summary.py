"""
Eden API - Summary Endpoint

GET /eden/summary - Get daily digest summary
"""

from datetime import datetime, timedelta
from typing import Optional

try:
    from python.helpers.api import ApiHandler
except ImportError:
    class ApiHandler:
        @classmethod
        def requires_auth(cls) -> bool:
            return True

from python.helpers.eden.models import DailySummary, TaskStatus, TaskCategory
from python.helpers.eden.clustering import ClusteringService


class SummaryHandler(ApiHandler):
    """Handle summary/digest requests."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    async def process(self, input: dict, request) -> dict:
        """Get daily summary."""
        service = ClusteringService.get_instance()
        stats = service.get_stats()

        # Get all tasks
        clusters = await service.get_clusters()
        all_tasks = []
        for cluster in clusters:
            all_tasks.extend(cluster.tasks)

        # Calculate category breakdown
        by_category = {}
        for cat in TaskCategory:
            count = sum(1 for t in all_tasks if t.category == cat)
            if count > 0:
                by_category[cat.value] = count

        # Get recent auto-handled
        recent_auto = [
            t for t in all_tasks
            if t.status == TaskStatus.AUTO_HANDLED and t.resolved_at
        ]
        recent_auto.sort(key=lambda t: t.resolved_at, reverse=True)

        # Get pending tasks
        pending_tasks = [
            t for t in all_tasks
            if t.status in [TaskStatus.PENDING, TaskStatus.NEEDS_REVIEW, TaskStatus.ESCALATED]
        ]
        pending_tasks.sort(key=lambda t: t.confidence)  # Most uncertain first

        summary = DailySummary(
            date=datetime.now(),
            auto_handled=stats["auto_handled"],
            pending_review=stats["pending"] + stats["needs_review"],
            escalated=stats["escalated"],
            completed=stats["completed"],
            total=stats["total_tasks"],
            by_category=by_category,
            recent_auto_handled=recent_auto[:10],
            pending_tasks=pending_tasks[:10],
        )

        return {"summary": summary.to_dict()}


# Handler for /eden/summary endpoint
Summary = SummaryHandler
