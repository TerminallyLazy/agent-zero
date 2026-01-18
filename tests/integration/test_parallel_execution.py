# tests/integration/test_parallel_execution.py
"""
Integration tests for parallel sub-agent task delegation.

These tests verify the complete parallel execution flow:
- Coordinator creation and DAG validation
- Worktree management
- Parallel agent spawning
- Dependency resolution
- Results consolidation
"""

import pytest
import tempfile
import os
import json
from unittest.mock import MagicMock, AsyncMock, patch

from python.helpers.parallel_coordinator import (
    ParallelCoordinator, TaskStatus
)
from python.helpers.git_worktree_manager import GitWorktreeManager


class TestParallelExecutionIntegration:
    """Integration tests for parallel execution system."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        agent = MagicMock()
        agent.data = {}
        agent.get_data = lambda key: agent.data.get(key)
        agent.set_data = lambda key, val: agent.data.__setitem__(key, val)
        agent.number = 0
        agent.agent_name = "A0"
        agent.context = MagicMock()
        return agent

    @pytest.fixture
    def temp_git_project(self):
        """Create a temporary git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize git repo
            os.system(f"cd {tmpdir} && git init && git config user.email 'test@test.com' && git config user.name 'Test'")

            # Create initial file and commit
            test_file = os.path.join(tmpdir, "README.md")
            with open(test_file, "w") as f:
                f.write("# Test Project\n")

            os.system(f"cd {tmpdir} && git add . && git commit -m 'Initial commit'")

            yield tmpdir

    def test_coordinator_and_worktree_integration(self, mock_agent, temp_git_project):
        """Test coordinator and worktree manager work together."""

        # Create task breakdown
        task_breakdown = [
            {"id": "task_001", "description": "First task"},
            {"id": "task_002", "description": "Second task", "dependencies": ["task_001"]},
        ]

        # Create coordinator
        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_git_project,
            task_breakdown=task_breakdown,
            coordination_mode="both",
        )

        # Create worktree manager
        wt_manager = GitWorktreeManager(temp_git_project, coordinator.coordinator_id)
        main_branch = wt_manager.ensure_repo_initialized()

        # Create worktrees for each task
        for task_id in coordinator.state.tasks:
            worktree_path = wt_manager.create_worktree(task_id, main_branch)
            coordinator.set_task_worktree(task_id, worktree_path)

            # Verify worktree exists
            assert os.path.exists(worktree_path)
            assert os.path.exists(os.path.join(worktree_path, "README.md"))

        # Verify coordinator state
        assert coordinator.state.worktrees["task_001"] is not None
        assert coordinator.state.worktrees["task_002"] is not None

        # Verify worktree listing
        worktrees = wt_manager.get_coordinator_worktrees()
        assert len(worktrees) == 2

        # Cleanup
        wt_manager.cleanup_coordinator_worktrees()
        coordinator.cleanup()

        # Verify cleanup
        worktrees = wt_manager.get_coordinator_worktrees()
        assert len(worktrees) == 0

    def test_dependency_driven_task_scheduling(self, mock_agent, temp_git_project):
        """Test that tasks are scheduled based on dependencies."""

        task_breakdown = [
            {"id": "independent_1", "description": "First independent task"},
            {"id": "independent_2", "description": "Second independent task"},
            {"id": "dependent", "description": "Depends on both",
             "dependencies": ["independent_1", "independent_2"]},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_git_project,
            task_breakdown=task_breakdown,
        )

        # Initially, only independent tasks should be ready
        ready = coordinator.get_ready_tasks()
        ready_ids = [t.task_id for t in ready]

        assert "independent_1" in ready_ids
        assert "independent_2" in ready_ids
        assert "dependent" not in ready_ids

        # Complete one independent task
        coordinator.update_task_status("independent_1", TaskStatus.COMPLETED)

        # Dependent still not ready (needs both)
        ready = coordinator.get_ready_tasks()
        ready_ids = [t.task_id for t in ready]
        assert "dependent" not in ready_ids

        # Complete second independent task
        coordinator.update_task_status("independent_2", TaskStatus.COMPLETED)

        # Now dependent should be ready
        ready = coordinator.get_ready_tasks()
        ready_ids = [t.task_id for t in ready]
        assert "dependent" in ready_ids

        coordinator.cleanup()

    def test_file_conflict_detection(self, mock_agent, temp_git_project):
        """Test that file conflicts are detected and prevented."""

        task_breakdown = [
            {"id": "task_001", "description": "First task"},
            {"id": "task_002", "description": "Second task"},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_git_project,
            task_breakdown=task_breakdown,
        )

        # Task 1 claims a file
        assert coordinator.claim_file("task_001", "A1", "src/shared.py")

        # Task 2 tries to claim same file - should be blocked
        assert not coordinator.claim_file("task_002", "A2", "src/shared.py")

        # Task 2 can claim a different file
        assert coordinator.claim_file("task_002", "A2", "src/other.py")

        # Conflict check returns the blocking task
        conflict = coordinator.check_file_conflict("task_002", "src/shared.py")
        assert conflict == "task_001"

        # After task 1 releases, task 2 can claim
        coordinator.release_file("task_001", "src/shared.py")
        assert coordinator.claim_file("task_002", "A2", "src/shared.py")

        coordinator.cleanup()

    def test_scratchpad_persistence(self, mock_agent, temp_git_project):
        """Test that scratchpad state persists across reloads."""

        task_breakdown = [
            {"id": "task_001", "description": "First task"},
        ]

        # Create and update coordinator
        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_git_project,
            task_breakdown=task_breakdown,
        )

        coordinator.update_task_status("task_001", TaskStatus.RUNNING)
        coordinator.set_task_agent("task_001", "A1")

        coordinator_id = coordinator.coordinator_id

        # Simulate reload by creating new coordinator instance
        mock_agent2 = MagicMock()
        mock_agent2.data = {}
        mock_agent2.get_data = lambda key: mock_agent2.data.get(key)
        mock_agent2.set_data = lambda key, val: mock_agent2.data.__setitem__(key, val)

        coordinator2 = ParallelCoordinator.load(
            mock_agent2,
            coordinator_id,
            temp_git_project,
        )

        # Verify state was preserved
        task = coordinator2.get_task("task_001")
        assert task.status == TaskStatus.RUNNING
        assert task.agent_name == "A1"

        coordinator.cleanup()
        coordinator2.cleanup()

    def test_worktree_merge_flow(self, mock_agent, temp_git_project):
        """Test the worktree merge workflow."""

        task_breakdown = [
            {"id": "task_001", "description": "Add feature A"},
        ]

        coordinator = ParallelCoordinator.create(
            agent=mock_agent,
            project_path=temp_git_project,
            task_breakdown=task_breakdown,
        )

        wt_manager = GitWorktreeManager(temp_git_project, coordinator.coordinator_id)
        main_branch = wt_manager.ensure_repo_initialized()

        # Create worktree
        worktree_path = wt_manager.create_worktree("task_001", main_branch)

        # Make changes in worktree
        new_file = os.path.join(worktree_path, "feature_a.py")
        with open(new_file, "w") as f:
            f.write("# Feature A\nprint('hello')\n")

        os.system(f"cd {worktree_path} && git add . && git commit -m 'Add feature A'")

        # Merge back to main
        branch_name = f"{wt_manager.BRANCH_PREFIX}/{coordinator.coordinator_id}/task_001"
        result = wt_manager.merge_worktree(branch_name, main_branch)

        assert result.success

        # Verify file exists in main
        main_file = os.path.join(temp_git_project, "feature_a.py")
        assert os.path.exists(main_file)

        wt_manager.cleanup_coordinator_worktrees()
        coordinator.cleanup()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
