"""
Eden API - Tasks Endpoints

GET /eden/tasks - List all tasks
GET /eden/tasks/:id - Get single task
POST /eden/tasks/:id/approve - Approve task action
POST /eden/tasks/:id/reject - Reject task
PUT /eden/tasks/:id/edit - Edit task draft
POST /eden/tasks/:id/escalate - Escalate task to physician
"""

from datetime import datetime
from typing import Optional

try:
    from python.helpers.api import ApiHandler
except ImportError:
    class ApiHandler:
        @classmethod
        def requires_auth(cls) -> bool:
            return True

from python.helpers.eden.models import (
    EdenTask,
    TaskCategory,
    TaskStatus,
)
from python.helpers.eden.clustering import ClusteringService
from python.helpers.eden.emr_adapter import get_adapter, Message


class TasksHandler(ApiHandler):
    """Handle task-related API requests."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    async def process(self, input: dict, request) -> dict:
        """Route task requests."""
        method = request.method
        task_id = input.get("id")
        action = input.get("action")

        if method == "GET":
            if task_id:
                return await self._get_task(task_id)
            else:
                return await self._list_tasks(input)

        elif method == "POST":
            if not task_id:
                return {"error": "Task ID required"}, 400

            if action == "approve":
                return await self._approve_task(task_id, input)
            elif action == "reject":
                return await self._reject_task(task_id, input)
            elif action == "escalate":
                return await self._escalate_task(task_id, input)

        elif method == "PUT":
            if task_id:
                return await self._edit_task(task_id, input)

        return {"error": "Method not allowed"}, 405

    async def _list_tasks(self, input: dict) -> dict:
        """List all tasks with filtering."""
        service = ClusteringService.get_instance()

        # Get all tasks from clusters
        clusters = await service.get_clusters()
        all_tasks = []
        for cluster in clusters:
            all_tasks.extend(cluster.tasks)

        # Apply filters
        status_filter = input.get("status")
        category_filter = input.get("category")
        patient_id = input.get("patient_id")

        if status_filter:
            status = TaskStatus(status_filter)
            all_tasks = [t for t in all_tasks if t.status == status]

        if category_filter:
            category = TaskCategory(category_filter)
            all_tasks = [t for t in all_tasks if t.category == category]

        if patient_id:
            all_tasks = [t for t in all_tasks if t.patient.id == patient_id]

        # Sort by received date (newest first)
        all_tasks.sort(key=lambda t: t.received_at, reverse=True)

        return {
            "tasks": [t.to_dict() for t in all_tasks],
            "count": len(all_tasks),
        }

    async def _get_task(self, task_id: str) -> dict:
        """Get single task by ID."""
        service = ClusteringService.get_instance()
        task = await service.get_task(task_id)

        if not task:
            return {"error": "Task not found"}, 404

        return {"task": task.to_dict()}

    async def _approve_task(self, task_id: str, input: dict) -> dict:
        """Approve a task's proposed action."""
        service = ClusteringService.get_instance()
        task = await service.get_task(task_id)

        if not task:
            return {"error": "Task not found"}, 404

        if task.status not in [TaskStatus.PENDING, TaskStatus.NEEDS_REVIEW]:
            return {"error": f"Cannot approve task in status {task.status.value}"}, 400

        # Execute the proposed action based on task type
        try:
            await self._execute_task_action(task)

            # Update status
            await service.update_task_status(
                task_id,
                TaskStatus.COMPLETED,
                resolved_by="physician",
            )

            return {
                "success": True,
                "task": task.to_dict(),
                "message": f"Task approved and executed: {task.proposed_action}",
            }

        except Exception as e:
            return {"error": f"Failed to execute action: {str(e)}"}, 500

    async def _execute_task_action(self, task: EdenTask):
        """Execute the approved action for a task."""
        # Get EMR adapter
        # adapter = get_adapter("drchrono")

        if task.category == TaskCategory.LAB:
            # Send lab results message to patient
            if task.draft_content:
                # await adapter.send_message(Message(
                #     patient_id=task.patient.id,
                #     subject=f"Your Lab Results - {task.title}",
                #     body=task.draft_content,
                # ))
                pass

        elif task.category == TaskCategory.MESSAGE:
            # Send response to patient message
            if task.draft_content:
                # await adapter.send_message(Message(
                #     patient_id=task.patient.id,
                #     subject=f"Re: {task.title}",
                #     body=task.draft_content,
                # ))
                pass

        elif task.category == TaskCategory.REFILL:
            # Approve refill
            # await adapter.approve_refill(
            #     medication_id=task.emr_id,
            #     quantity=task.raw_content.get("quantity", 30),
            #     refills=task.raw_content.get("refills", 3),
            # )
            pass

        # Mark as processed in EMR
        # await adapter.mark_item_processed(task.emr_id)

    async def _reject_task(self, task_id: str, input: dict) -> dict:
        """Reject a task."""
        service = ClusteringService.get_instance()
        task = await service.get_task(task_id)

        if not task:
            return {"error": "Task not found"}, 404

        reason = input.get("reason", "Rejected by physician")

        # Update status
        await service.update_task_status(
            task_id,
            TaskStatus.REJECTED,
            resolved_by="physician",
        )

        # For refills, deny in EMR
        if task.category == TaskCategory.REFILL:
            # adapter = get_adapter("drchrono")
            # await adapter.deny_refill(task.emr_id, reason)
            pass

        return {
            "success": True,
            "task": task.to_dict(),
            "message": f"Task rejected: {reason}",
        }

    async def _escalate_task(self, task_id: str, input: dict) -> dict:
        """Escalate a task for physician review."""
        service = ClusteringService.get_instance()
        task = await service.get_task(task_id)

        if not task:
            return {"error": "Task not found"}, 404

        # Update status
        await service.update_task_status(
            task_id,
            TaskStatus.ESCALATED,
        )

        # Reduce confidence to ensure it stays escalated
        task.confidence = min(task.confidence, 0.50)

        return {
            "success": True,
            "task": task.to_dict(),
            "message": "Task escalated for physician review",
        }

    async def _edit_task(self, task_id: str, input: dict) -> dict:
        """Edit a task's draft content."""
        service = ClusteringService.get_instance()
        task = await service.get_task(task_id)

        if not task:
            return {"error": "Task not found"}, 404

        # Update draft
        new_draft = input.get("draft_content")
        new_action = input.get("proposed_action")

        if new_draft:
            task.draft_content = new_draft
        if new_action:
            task.proposed_action = new_action

        # Change status to needs_review if was auto_handled
        if task.status == TaskStatus.AUTO_HANDLED:
            task.status = TaskStatus.NEEDS_REVIEW

        return {
            "success": True,
            "task": task.to_dict(),
            "message": "Task updated",
        }


# Handler for /eden/tasks endpoint
Tasks = TasksHandler
