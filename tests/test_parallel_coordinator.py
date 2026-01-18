# tests/test_parallel_coordinator.py
import pytest
import tempfile
import os
import json
from unittest.mock import MagicMock, patch

from python.helpers.parallel_coordinator import (
    TaskStatus, SubTaskInfo, CoordinatorState, ParallelCoordinator
)


class TestTaskStatus:
    def test_enum_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.ERROR.value == "error"
        assert TaskStatus.BLOCKED.value == "blocked"


class TestSubTaskInfo:
    def test_to_dict(self):
        task = SubTaskInfo(
            task_id="task_001",
            description="Test task",
            dependencies=["task_000"],
            status=TaskStatus.RUNNING,
        )
        d = task.to_dict()
        assert d["task_id"] == "task_001"
        assert d["status"] == "running"
        assert d["dependencies"] == ["task_000"]

    def test_from_dict(self):
        d = {
            "task_id": "task_002",
            "description": "Another task",
            "profile": "developer",
            "dependencies": [],
            "status": "completed",
            "agent_name": "A1",
            "worktree_path": "/tmp/wt",
            "started_at": "2026-01-17T00:00:00Z",
            "completed_at": "2026-01-17T01:00:00Z",
            "output": "Done",
            "error": "",
        }
        task = SubTaskInfo.from_dict(d)
        assert task.task_id == "task_002"
        assert task.status == TaskStatus.COMPLETED
        assert task.output == "Done"


class TestCoordinatorState:
    def test_to_dict_and_from_dict(self):
        state = CoordinatorState(
            coordinator_id="coord_abc123",
            project_name="test_project",
            main_branch="main",
            coordination_mode="both",
            merge_strategy="sequential",
            created_at="2026-01-17T00:00:00Z",
            tasks={
                "task_001": SubTaskInfo(task_id="task_001", description="First"),
            },
            worktrees={"task_001": "/tmp/wt1"},
        )

        d = state.to_dict()
        restored = CoordinatorState.from_dict(d)

        assert restored.coordinator_id == "coord_abc123"
        assert restored.tasks["task_001"].description == "First"
        assert restored.worktrees["task_001"] == "/tmp/wt1"


class TestParallelCoordinator:
    @pytest.fixture
    def mock_agent(self):
        agent = MagicMock()
        agent.data = {}
        agent.get_data = lambda key: agent.data.get(key)
        agent.set_data = lambda key, val: agent.data.__setitem__(key, val)
        return agent

    @pytest.fixture
    def temp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_create_coordinator(self, mock_agent, temp_project):
        task_breakdown = [
            {"id": "task_001", "description": "First task"},
            {"id": "task_002", "description": "Second task", "dependencies": ["task_001"]},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_project,
            task_breakdown=task_breakdown,
        )

        assert coordinator.coordinator_id.startswith("coord_")
        assert len(coordinator.state.tasks) == 2
        assert coordinator.state.tasks["task_001"].status == TaskStatus.PENDING

    def test_validate_dag_valid(self, mock_agent, temp_project):
        task_breakdown = [
            {"id": "task_001", "description": "First"},
            {"id": "task_002", "description": "Second", "dependencies": ["task_001"]},
            {"id": "task_003", "description": "Third", "dependencies": ["task_001", "task_002"]},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_project,
            task_breakdown=task_breakdown,
        )

        is_valid, error = coordinator.validate_dag()
        assert is_valid
        assert error == ""

    def test_validate_dag_circular(self, mock_agent, temp_project):
        task_breakdown = [
            {"id": "task_001", "description": "First", "dependencies": ["task_003"]},
            {"id": "task_002", "description": "Second", "dependencies": ["task_001"]},
            {"id": "task_003", "description": "Third", "dependencies": ["task_002"]},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_project,
            task_breakdown=task_breakdown,
        )

        is_valid, error = coordinator.validate_dag()
        assert not is_valid
        assert "Circular dependency" in error

    def test_validate_dag_missing_dep(self, mock_agent, temp_project):
        task_breakdown = [
            {"id": "task_001", "description": "First", "dependencies": ["nonexistent"]},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_project,
            task_breakdown=task_breakdown,
        )

        is_valid, error = coordinator.validate_dag()
        assert not is_valid
        assert "unknown task" in error

    def test_get_ready_tasks(self, mock_agent, temp_project):
        task_breakdown = [
            {"id": "task_001", "description": "First"},
            {"id": "task_002", "description": "Second", "dependencies": ["task_001"]},
            {"id": "task_003", "description": "Third"},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_project,
            task_breakdown=task_breakdown,
        )

        # Initially, task_001 and task_003 should be ready (no deps)
        ready = coordinator.get_ready_tasks()
        ready_ids = [t.task_id for t in ready]
        assert "task_001" in ready_ids
        assert "task_003" in ready_ids
        assert "task_002" not in ready_ids

        # Mark task_001 as completed
        coordinator.update_task_status("task_001", TaskStatus.COMPLETED)

        # Now task_002 should also be ready
        ready = coordinator.get_ready_tasks()
        ready_ids = [t.task_id for t in ready]
        assert "task_002" in ready_ids

    def test_file_claim_and_conflict(self, mock_agent, temp_project):
        task_breakdown = [
            {"id": "task_001", "description": "First"},
            {"id": "task_002", "description": "Second"},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_project,
            task_breakdown=task_breakdown,
        )

        # Task 1 claims a file
        assert coordinator.claim_file("task_001", "A1", "src/main.py")

        # Task 2 tries to claim same file - should fail
        assert not coordinator.claim_file("task_002", "A2", "src/main.py")

        # Check conflict detection
        conflict = coordinator.check_file_conflict("task_002", "src/main.py")
        assert conflict == "task_001"

        # Task 1 releases file
        coordinator.release_file("task_001", "src/main.py")

        # Now task 2 can claim it
        assert coordinator.claim_file("task_002", "A2", "src/main.py")

    def test_update_task_status(self, mock_agent, temp_project):
        task_breakdown = [
            {"id": "task_001", "description": "First"},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_project,
            task_breakdown=task_breakdown,
        )

        # Update to running
        coordinator.update_task_status("task_001", TaskStatus.RUNNING)
        task = coordinator.get_task("task_001")
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

        # Update to completed with output
        coordinator.update_task_status("task_001", TaskStatus.COMPLETED, output="Done!")
        task = coordinator.get_task("task_001")
        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at is not None
        assert task.output == "Done!"

    def test_scratchpad_summary(self, mock_agent, temp_project):
        task_breakdown = [
            {"id": "task_001", "description": "Build frontend component"},
            {"id": "task_002", "description": "Build backend API", "dependencies": ["task_001"]},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_project,
            task_breakdown=task_breakdown,
        )

        coordinator.update_task_status("task_001", TaskStatus.RUNNING)
        coordinator.set_task_agent("task_001", "A1")

        summary = coordinator.get_scratchpad_summary()

        assert "Parallel Task Coordination" in summary
        assert "task_001" in summary
        assert "A1" in summary
        assert "Running: 1" in summary
