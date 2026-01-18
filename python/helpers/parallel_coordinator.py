"""
Parallel Coordinator Helper

Manages state and coordination for parallel sub-agent task execution.
Provides:
- Task status tracking via JSON files
- Dependency resolution for task scheduling
- File registry for conflict prevention
- Coordination logging to Memory system
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING
import json
import os
import threading
import uuid

from filelock import FileLock

from python.helpers import files, memory

if TYPE_CHECKING:
    from agent import Agent


class TaskStatus(Enum):
    """Status of a parallel sub-task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    BLOCKED = "blocked"


@dataclass
class SubTaskInfo:
    """Information about a single parallel sub-task."""
    task_id: str
    description: str
    profile: str = "default"
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    agent_name: str = ""
    worktree_path: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SubTaskInfo":
        """Create from dict."""
        d = d.copy()
        d["status"] = TaskStatus(d.get("status", "pending"))
        return cls(**d)


@dataclass
class FileRegistryEntry:
    """Tracks which agent is working on which file."""
    file_path: str
    claimed_by: str  # task_id
    agent_name: str
    claimed_at: str
    status: str = "in_progress"  # in_progress | completed


@dataclass
class CoordinatorState:
    """Central coordination state for parallel execution."""
    coordinator_id: str
    project_name: str
    main_branch: str
    coordination_mode: str  # scratchpad | git_worktree | both
    merge_strategy: str  # sequential | parallel_safe
    created_at: str
    tasks: dict[str, SubTaskInfo] = field(default_factory=dict)
    worktrees: dict[str, str] = field(default_factory=dict)  # task_id -> path

    def to_dict(self) -> dict:
        d = {
            "coordinator_id": self.coordinator_id,
            "project_name": self.project_name,
            "main_branch": self.main_branch,
            "coordination_mode": self.coordination_mode,
            "merge_strategy": self.merge_strategy,
            "created_at": self.created_at,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "worktrees": self.worktrees,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CoordinatorState":
        tasks = {k: SubTaskInfo.from_dict(v) for k, v in d.get("tasks", {}).items()}
        return cls(
            coordinator_id=d["coordinator_id"],
            project_name=d["project_name"],
            main_branch=d["main_branch"],
            coordination_mode=d["coordination_mode"],
            merge_strategy=d["merge_strategy"],
            created_at=d["created_at"],
            tasks=tasks,
            worktrees=d.get("worktrees", {}),
        )


class ParallelCoordinator:
    """
    Manages parallel sub-agent coordination.

    Stores state in:
    - {project}/.a0proj/parallel/{coordinator_id}/coordinator_state.json
    - {project}/.a0proj/parallel/{coordinator_id}/task_{id}_status.json
    - {project}/.a0proj/parallel/{coordinator_id}/file_registry.json
    """

    DATA_KEY = "_parallel_coordinator"

    def __init__(self, agent: "Agent", coordinator_id: str, project_path: str):
        self.agent = agent
        self.coordinator_id = coordinator_id
        self.project_path = project_path
        self.scratchpad_path = os.path.join(
            project_path, ".a0proj", "parallel", coordinator_id
        )
        self._state: Optional[CoordinatorState] = None
        # Thread safety: RLock allows nested acquisition from same thread
        self._state_lock = threading.RLock()
        # File-based lock for cross-process file registry synchronization
        self._registry_lock_path = os.path.join(
            project_path, ".a0proj", "parallel", f"{coordinator_id}_registry.lock"
        )

    @classmethod
    def create(
        cls,
        agent: "Agent",
        project_path: str,
        task_breakdown: list[dict],
        coordination_mode: str = "both",
        merge_strategy: str = "sequential",
        main_branch: str = "main",
    ) -> "ParallelCoordinator":
        """Create a new coordinator for parallel task execution."""
        coordinator_id = f"coord_{uuid.uuid4().hex[:8]}"

        coordinator = cls(agent, coordinator_id, project_path)

        # Create scratchpad directory
        files.create_dir_safe(coordinator.scratchpad_path)

        # Extract project name from path
        project_name = os.path.basename(project_path)

        # Initialize state
        state = CoordinatorState(
            coordinator_id=coordinator_id,
            project_name=project_name,
            main_branch=main_branch,
            coordination_mode=coordination_mode,
            merge_strategy=merge_strategy,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Register tasks
        for task_dict in task_breakdown:
            task = SubTaskInfo(
                task_id=task_dict["id"],
                description=task_dict["description"],
                profile=task_dict.get("profile", "default"),
                dependencies=task_dict.get("dependencies", []),
            )
            state.tasks[task.task_id] = task

        coordinator._state = state
        coordinator._save_state()
        coordinator._init_file_registry()

        # Store reference in agent data
        agent.set_data(cls.DATA_KEY, coordinator)

        return coordinator

    @classmethod
    def get(cls, agent: "Agent") -> Optional["ParallelCoordinator"]:
        """Get the coordinator from agent's data if it exists."""
        return agent.get_data(cls.DATA_KEY)

    @classmethod
    def load(
        cls, agent: "Agent", coordinator_id: str, project_path: str
    ) -> "ParallelCoordinator":
        """Load an existing coordinator from disk."""
        coordinator = cls(agent, coordinator_id, project_path)
        coordinator._load_state()
        agent.set_data(cls.DATA_KEY, coordinator)
        return coordinator

    def _save_state(self) -> None:
        """Save coordinator state to JSON file. Must be called with _state_lock held."""
        if not self._state:
            return
        state_path = os.path.join(self.scratchpad_path, "coordinator_state.json")
        files.write_file(state_path, json.dumps(self._state.to_dict(), indent=2))

    def _load_state(self) -> None:
        """Load coordinator state from JSON file. Must be called with _state_lock held."""
        state_path = os.path.join(self.scratchpad_path, "coordinator_state.json")
        content = files.read_file(state_path)
        self._state = CoordinatorState.from_dict(json.loads(content))

    def _init_file_registry(self) -> None:
        """Initialize empty file registry."""
        registry_path = os.path.join(self.scratchpad_path, "file_registry.json")
        files.write_file(registry_path, json.dumps({"files": {}, "conflicts": []}, indent=2))

    @property
    def state(self) -> CoordinatorState:
        """Get current coordinator state (thread-safe)."""
        with self._state_lock:
            if not self._state:
                self._load_state()
            return self._state  # type: ignore

    def get_task(self, task_id: str) -> Optional[SubTaskInfo]:
        """Get task info by ID (thread-safe)."""
        with self._state_lock:
            return self.state.tasks.get(task_id)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        output: str = "",
        error: str = "",
    ) -> None:
        """Update a task's status and save to scratchpad (thread-safe)."""
        with self._state_lock:
            task = self.state.tasks.get(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")

            task.status = status

            if status == TaskStatus.RUNNING and not task.started_at:
                task.started_at = datetime.now(timezone.utc).isoformat()
            elif status in (TaskStatus.COMPLETED, TaskStatus.ERROR):
                task.completed_at = datetime.now(timezone.utc).isoformat()

            if output:
                task.output = output
            if error:
                task.error = error

            # Save task-specific status file (atomic per-task writes)
            task_status_path = os.path.join(
                self.scratchpad_path, f"task_{task_id}_status.json"
            )
            files.write_file(task_status_path, json.dumps(task.to_dict(), indent=2))

            # Update main state
            self._save_state()

    def set_task_agent(self, task_id: str, agent_name: str) -> None:
        """Associate an agent with a task (thread-safe)."""
        with self._state_lock:
            task = self.state.tasks.get(task_id)
            if task:
                task.agent_name = agent_name
                self._save_state()

    def set_task_worktree(self, task_id: str, worktree_path: str) -> None:
        """Associate a worktree with a task (thread-safe)."""
        with self._state_lock:
            task = self.state.tasks.get(task_id)
            if task:
                task.worktree_path = worktree_path
                self.state.worktrees[task_id] = worktree_path
                self._save_state()

    def get_ready_tasks(self) -> list[SubTaskInfo]:
        """Get tasks that are ready to start (dependencies satisfied, thread-safe)."""
        with self._state_lock:
            ready = []
            completed_ids = {
                tid for tid, t in self.state.tasks.items()
                if t.status == TaskStatus.COMPLETED
            }

            for task in self.state.tasks.values():
                if task.status != TaskStatus.PENDING:
                    continue

                # Check if all dependencies are completed
                deps_satisfied = all(
                    dep_id in completed_ids
                    for dep_id in task.dependencies
                )

                if deps_satisfied:
                    ready.append(task)

            return ready

    def get_running_tasks(self) -> list[SubTaskInfo]:
        """Get tasks currently running (thread-safe)."""
        with self._state_lock:
            return [
                t for t in self.state.tasks.values()
                if t.status == TaskStatus.RUNNING
            ]

    def get_completed_tasks(self) -> list[SubTaskInfo]:
        """Get completed tasks (thread-safe)."""
        with self._state_lock:
            return [
                t for t in self.state.tasks.values()
                if t.status == TaskStatus.COMPLETED
            ]

    def all_tasks_complete(self) -> bool:
        """Check if all tasks are completed or errored (thread-safe)."""
        with self._state_lock:
            return all(
                t.status in (TaskStatus.COMPLETED, TaskStatus.ERROR)
                for t in self.state.tasks.values()
            )

    def has_errors(self) -> bool:
        """Check if any task has errored (thread-safe)."""
        with self._state_lock:
            return any(
                t.status == TaskStatus.ERROR
                for t in self.state.tasks.values()
            )

    def validate_dag(self) -> tuple[bool, str]:
        """
        Validate task dependencies form a valid DAG (no cycles, thread-safe).
        Returns (is_valid, error_message).
        """
        with self._state_lock:
            task_ids = set(self.state.tasks.keys())

            # Check all dependencies exist
            for task in self.state.tasks.values():
                for dep_id in task.dependencies:
                    if dep_id not in task_ids:
                        return False, f"Task {task.task_id} depends on unknown task {dep_id}"

            # Topological sort to detect cycles
            visited = set()
            rec_stack = set()

            def has_cycle(task_id: str) -> bool:
                visited.add(task_id)
                rec_stack.add(task_id)

                task = self.state.tasks[task_id]
                for dep_id in task.dependencies:
                    if dep_id not in visited:
                        if has_cycle(dep_id):
                            return True
                    elif dep_id in rec_stack:
                        return True

                rec_stack.remove(task_id)
                return False

            for task_id in task_ids:
                if task_id not in visited:
                    if has_cycle(task_id):
                        return False, f"Circular dependency detected involving task {task_id}"

            return True, ""

    # File Registry Methods (with file-based locking for cross-process safety)

    def _get_registry_lock(self) -> FileLock:
        """Get a file lock for the registry. Ensures lock directory exists."""
        lock_dir = os.path.dirname(self._registry_lock_path)
        if not os.path.exists(lock_dir):
            files.create_dir_safe(lock_dir)
        return FileLock(self._registry_lock_path, timeout=10)

    def claim_file(self, task_id: str, agent_name: str, file_path: str) -> bool:
        """
        Claim a file for a task. Returns False if already claimed by another task.
        Thread-safe with file-based locking for cross-process coordination.
        """
        with self._get_registry_lock():
            registry = self._load_file_registry()

            existing = registry["files"].get(file_path)
            if existing and existing["status"] == "in_progress":
                if existing["claimed_by"] != task_id:
                    # Conflict!
                    return False

            registry["files"][file_path] = {
                "claimed_by": task_id,
                "agent_name": agent_name,
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "status": "in_progress",
            }

            self._save_file_registry(registry)
            return True

    def release_file(self, task_id: str, file_path: str) -> None:
        """Mark a file claim as completed (thread-safe with file locking)."""
        with self._get_registry_lock():
            registry = self._load_file_registry()

            existing = registry["files"].get(file_path)
            if existing and existing["claimed_by"] == task_id:
                existing["status"] = "completed"
                self._save_file_registry(registry)

    def check_file_conflict(self, task_id: str, file_path: str) -> Optional[str]:
        """
        Check if a file is claimed by another task (thread-safe with file locking).
        Returns the claiming task_id if conflict, None otherwise.
        """
        with self._get_registry_lock():
            registry = self._load_file_registry()

            existing = registry["files"].get(file_path)
            if existing and existing["status"] == "in_progress":
                if existing["claimed_by"] != task_id:
                    return existing["claimed_by"]

            return None

    def _load_file_registry(self) -> dict[str, Any]:
        """Load file registry from JSON. Must be called with registry lock held."""
        registry_path = os.path.join(self.scratchpad_path, "file_registry.json")
        try:
            content = files.read_file(registry_path)
            return json.loads(content)
        except Exception:
            return {"files": {}, "conflicts": []}

    def _save_file_registry(self, registry: dict[str, Any]) -> None:
        """Save file registry to JSON. Must be called with registry lock held."""
        registry_path = os.path.join(self.scratchpad_path, "file_registry.json")
        files.write_file(registry_path, json.dumps(registry, indent=2))

    # Scratchpad Summary Methods

    def get_scratchpad_summary(self) -> str:
        """Get a human-readable summary of current coordination state (thread-safe)."""
        with self._state_lock:
            lines = ["## Parallel Task Coordination Status\n"]

            # Task overview
            completed = len([t for t in self.state.tasks.values() if t.status == TaskStatus.COMPLETED])
            running = len([t for t in self.state.tasks.values() if t.status == TaskStatus.RUNNING])
            pending = len([t for t in self.state.tasks.values() if t.status == TaskStatus.PENDING])
            errors = len([t for t in self.state.tasks.values() if t.status == TaskStatus.ERROR])
            total = len(self.state.tasks)

            lines.append(f"**Progress:** {completed}/{total} tasks completed")
            lines.append(f"- Running: {running}")
            lines.append(f"- Pending: {pending}")
            if errors:
                lines.append(f"- Errors: {errors}")
            lines.append("")

            # Task details
            lines.append("**Tasks:**")
            for task in self.state.tasks.values():
                status_icon = {
                    TaskStatus.PENDING: "?",
                    TaskStatus.RUNNING: "~",
                    TaskStatus.COMPLETED: "+",
                    TaskStatus.ERROR: "x",
                    TaskStatus.BLOCKED: "!",
                }.get(task.status, "?")

                deps = f" (deps: {', '.join(task.dependencies)})" if task.dependencies else ""
                agent = f" [{task.agent_name}]" if task.agent_name else ""
                lines.append(f"- {status_icon} {task.task_id}: {task.description[:50]}...{deps}{agent}")

        # File registry conflicts (separate lock)
        with self._get_registry_lock():
            registry = self._load_file_registry()
            if registry.get("conflicts"):
                lines.append("\n**File Conflicts:**")
                for conflict in registry["conflicts"]:
                    lines.append(f"- {conflict['file']}: claimed by {', '.join(conflict['tasks'])}")

        return "\n".join(lines)

    def cleanup(self) -> None:
        """Clean up coordinator resources."""
        # Remove from agent data
        if self.agent.get_data(self.DATA_KEY):
            self.agent.set_data(self.DATA_KEY, None)

        # Archive scratchpad (don't delete, useful for debugging)
        archive_path = os.path.join(
            self.project_path, ".a0proj", "parallel_archive", self.coordinator_id
        )
        if files.exists(self.scratchpad_path):
            files.create_dir_safe(os.path.dirname(archive_path))
            os.rename(self.scratchpad_path, archive_path)
