"""
Eden Clinical Inboxologist - Clustering Service

Groups inbox items into patient-centric clusters.
"""

from datetime import datetime
from typing import Optional
import uuid

from .models import (
    Cluster,
    EdenTask,
    Patient,
    TaskCategory,
    TaskStatus,
    ConfidenceFactor,
)
from .emr_adapter import InboxItem


class ClusteringService:
    """
    Service for managing patient clusters.

    Clusters group related inbox items by patient,
    making it easier to review all items for a patient at once.
    """

    _instance: Optional["ClusteringService"] = None

    def __init__(self):
        self.clusters: dict[str, Cluster] = {}
        self.tasks: dict[str, EdenTask] = {}

    @classmethod
    def get_instance(cls) -> "ClusteringService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def process_inbox_items(self, items: list[InboxItem]) -> list[Cluster]:
        """
        Process inbox items into clusters.

        Args:
            items: List of inbox items from EMR

        Returns:
            List of updated clusters
        """
        updated_clusters = set()

        for item in items:
            task = self._create_task(item)
            self.tasks[task.id] = task

            # Find or create cluster for this patient
            cluster = self._get_or_create_cluster(item.patient_id, item.patient_name)
            cluster.tasks.append(task)
            updated_clusters.add(cluster.id)

        # Update cluster reasoning
        for cluster_id in updated_clusters:
            cluster = self.clusters[cluster_id]
            cluster.reasoning = self._generate_cluster_reasoning(cluster)

        return [self.clusters[cid] for cid in updated_clusters]

    def _create_task(self, item: InboxItem) -> EdenTask:
        """Create an EdenTask from an InboxItem."""
        patient = Patient(
            id=item.patient_id,
            name=item.patient_name,
            dob="",  # Would be fetched from EMR
        )

        return EdenTask(
            id=str(uuid.uuid4()),
            category=item.to_task_category(),
            status=TaskStatus.PENDING,
            confidence=0.5,  # Will be calculated by confidence scorer
            emr_id=item.emr_id,
            patient=patient,
            received_at=item.received_at,
            title=item.title,
            summary=item.content[:200],  # Truncate for summary
            raw_content=item.raw_data,
        )

    def _get_or_create_cluster(self, patient_id: str, patient_name: str) -> Cluster:
        """Get existing cluster or create new one for patient."""
        # Look for existing cluster by patient ID
        for cluster in self.clusters.values():
            if cluster.patient.id == patient_id:
                return cluster

        # Create new cluster
        patient = Patient(
            id=patient_id,
            name=patient_name,
            dob="",
        )

        cluster = Cluster(
            id=str(uuid.uuid4()),
            patient=patient,
            tasks=[],
        )

        self.clusters[cluster.id] = cluster
        return cluster

    def _generate_cluster_reasoning(self, cluster: Cluster) -> list[str]:
        """Generate reasoning summary for cluster."""
        reasoning = []
        reasoning.append(f"Cluster for {cluster.patient.name}")

        # Count by status
        status_counts = {}
        for task in cluster.tasks:
            status_counts[task.status] = status_counts.get(task.status, 0) + 1

        # Count by category
        category_counts = {}
        for task in cluster.tasks:
            category_counts[task.category] = category_counts.get(task.category, 0) + 1

        # Summarize
        if any(t.status == TaskStatus.ESCALATED for t in cluster.tasks):
            reasoning.append("⚠ Contains escalated items requiring review")
        elif any(t.status == TaskStatus.NEEDS_REVIEW for t in cluster.tasks):
            reasoning.append("⚠ Contains items needing review")
        else:
            reasoning.append("✓ All items routine")

        reasoning.append(f"→ Average Confidence: {int(cluster.avg_confidence * 100)}%")

        return reasoning

    async def get_clusters(self) -> list[Cluster]:
        """Get all clusters."""
        return list(self.clusters.values())

    async def get_cluster(self, cluster_id: str) -> Optional[Cluster]:
        """Get cluster by ID."""
        return self.clusters.get(cluster_id)

    async def get_task(self, task_id: str) -> Optional[EdenTask]:
        """Get task by ID."""
        return self.tasks.get(task_id)

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        resolved_by: Optional[str] = None,
    ) -> Optional[EdenTask]:
        """Update task status."""
        task = self.tasks.get(task_id)
        if task:
            task.status = status
            if status in [TaskStatus.COMPLETED, TaskStatus.AUTO_HANDLED]:
                task.resolved_at = datetime.now()
                task.resolved_by = resolved_by or "eden"
        return task

    async def update_task_confidence(
        self,
        task_id: str,
        confidence: float,
        factors: list[ConfidenceFactor],
        reasoning: list[str],
    ) -> Optional[EdenTask]:
        """Update task confidence score and reasoning."""
        task = self.tasks.get(task_id)
        if task:
            task.confidence = confidence
            task.confidence_factors = factors
            task.reasoning = reasoning

            # Auto-update status based on confidence
            if confidence >= 0.85 and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.AUTO_HANDLED
                task.resolved_at = datetime.now()
                task.resolved_by = "eden"
            elif confidence < 0.60 and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.ESCALATED

        return task

    async def set_task_draft(
        self,
        task_id: str,
        draft_content: str,
        proposed_action: str,
    ) -> Optional[EdenTask]:
        """Set draft content for a task."""
        task = self.tasks.get(task_id)
        if task:
            task.draft_content = draft_content
            task.proposed_action = proposed_action
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.NEEDS_REVIEW
        return task

    def clear(self):
        """Clear all clusters and tasks."""
        self.clusters.clear()
        self.tasks.clear()

    def get_stats(self) -> dict:
        """Get summary statistics."""
        all_tasks = list(self.tasks.values())

        return {
            "total_clusters": len(self.clusters),
            "total_tasks": len(all_tasks),
            "auto_handled": sum(1 for t in all_tasks if t.status == TaskStatus.AUTO_HANDLED),
            "pending": sum(1 for t in all_tasks if t.status == TaskStatus.PENDING),
            "needs_review": sum(1 for t in all_tasks if t.status == TaskStatus.NEEDS_REVIEW),
            "escalated": sum(1 for t in all_tasks if t.status == TaskStatus.ESCALATED),
            "completed": sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED),
        }
