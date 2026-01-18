"""
Parallel Delegate Tool

Orchestrates parallel sub-agent task execution with coordination.
Uses subprocess for complete isolation to avoid event loop conflicts.
"""

import asyncio
import json
import os
import sys
from typing import Any, Optional
from dataclasses import dataclass
from pathlib import Path

from python.helpers.tool import Tool, Response
from python.helpers.parallel_coordinator import (
    ParallelCoordinator, TaskStatus, SubTaskInfo
)
from python.helpers.git_worktree_manager import GitWorktreeManager
from python.helpers import projects


@dataclass
class TaskResult:
    """Result from a parallel task execution."""
    task_id: str
    success: bool
    result: str
    error: Optional[str] = None


class ParallelDelegate(Tool):
    """
    Delegate tasks to multiple subordinate agents working in parallel.

    Tool Arguments:
        task_breakdown: List of task definitions with id, description, profile, dependencies
        coordination_mode: "scratchpad" | "git_worktree" | "both" (default: "both")
        merge_strategy: "sequential" | "parallel_safe" (default: "sequential")
    """

    # Coordinator data key for storing active parallel sessions
    DATA_KEY_COORDINATOR = "_parallel_delegate_coordinator"
    DATA_KEY_AGENT_TASKS = "_parallel_delegate_agent_tasks"

    # Timeout for each task (in seconds)
    TASK_TIMEOUT = 300  # 5 minutes per task

    # Path to the worker script
    WORKER_SCRIPT = Path(__file__).parent / "_parallel_worker.py"

    async def execute(self, **kwargs) -> Response:
        # Parse arguments
        task_breakdown = self._parse_task_breakdown(kwargs.get("task_breakdown", "[]"))
        coordination_mode = kwargs.get("coordination_mode", "both")
        merge_strategy = kwargs.get("merge_strategy", "sequential")

        # Validate inputs
        if not task_breakdown:
            return Response(
                message="Error: task_breakdown is required and must contain at least one task.",
                break_loop=False,
            )

        # Get project context
        project_name = projects.get_context_project_name(self.agent.context)
        if not project_name:
            return Response(
                message="Error: Parallel delegation requires an active project context. "
                        "Please create or select a project first.",
                break_loop=False,
            )

        project_path = projects.get_project_folder(project_name)

        # Create coordinator
        coordinator = ParallelCoordinator.create(
            agent=self.agent,
            project_path=project_path,
            task_breakdown=task_breakdown,
            coordination_mode=coordination_mode,
            merge_strategy=merge_strategy,
        )

        # Validate DAG
        is_valid, error = coordinator.validate_dag()
        if not is_valid:
            coordinator.cleanup()
            return Response(
                message=f"Error: Invalid task dependencies - {error}",
                break_loop=False,
            )

        # Initialize git worktrees if needed
        worktree_manager = None
        if coordination_mode in ("git_worktree", "both"):
            try:
                worktree_manager = GitWorktreeManager(project_path, coordinator.coordinator_id)
                main_branch = worktree_manager.ensure_repo_initialized()

                # Create worktree for each task
                for task_id in coordinator.state.tasks:
                    worktree_path = worktree_manager.create_worktree(task_id, main_branch)
                    coordinator.set_task_worktree(task_id, worktree_path)
            except Exception as e:
                coordinator.cleanup()
                return Response(
                    message=f"Error initializing git worktrees: {str(e)}",
                    break_loop=False,
                )

        # Store coordinator in agent data
        self.agent.set_data(self.DATA_KEY_COORDINATOR, coordinator)

        # Execute tasks in parallel using subprocess
        try:
            result = await self._execute_parallel_tasks(coordinator, worktree_manager)
        except Exception as e:
            # Cleanup on error
            if worktree_manager:
                try:
                    worktree_manager.cleanup_coordinator_worktrees()
                except Exception:
                    pass
            coordinator.cleanup()
            return Response(
                message=f"Error during parallel execution: {str(e)}",
                break_loop=False,
            )

        # Merge worktrees if all tasks succeeded
        merge_report = ""
        if worktree_manager and not coordinator.has_errors():
            try:
                merge_report = await self._merge_worktrees(coordinator, worktree_manager)
            except Exception as e:
                merge_report = f"### Merge Error\n\nFailed to merge worktrees: {str(e)}"

        # Cleanup
        if worktree_manager:
            try:
                worktree_manager.cleanup_coordinator_worktrees()
            except Exception:
                pass
        coordinator.cleanup()

        return Response(
            message=f"## Parallel Execution Complete\n\n{result}\n\n{merge_report}",
            break_loop=False,
        )

    def _parse_task_breakdown(self, raw: Any) -> list[dict]:
        """Parse task breakdown from string or list."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return []
        return []

    async def _execute_parallel_tasks(
        self,
        coordinator: ParallelCoordinator,
        worktree_manager: Optional[GitWorktreeManager],
    ) -> str:
        """Execute tasks in parallel using subprocess for complete isolation."""

        # Track active subprocesses: task_id -> (process, start_time)
        active_processes: dict[str, tuple[asyncio.subprocess.Process, float]] = {}
        results: dict[str, str] = {}

        while not coordinator.all_tasks_complete():
            # Get tasks ready to start
            ready_tasks = coordinator.get_ready_tasks()

            # Start ready tasks as separate subprocesses
            for task_info in ready_tasks:
                if task_info.task_id not in active_processes:
                    # Build task message
                    message = self._build_task_message(coordinator, task_info)

                    # Prepare input for worker
                    worker_input = json.dumps({
                        "task_id": task_info.task_id,
                        "message": message,
                        "profile": task_info.profile or "default",
                        "agent_number": self.agent.number + 1,
                        "coordinator_id": coordinator.coordinator_id,
                        "worktree_path": task_info.worktree_path or "null",
                        "scratchpad_path": coordinator.scratchpad_path,
                    })

                    # Start subprocess with the worker script
                    # Inherit environment and ensure project root is in PYTHONPATH
                    env = os.environ.copy()
                    project_root = os.getcwd()
                    pythonpath = env.get("PYTHONPATH", "")
                    if project_root not in pythonpath:
                        env["PYTHONPATH"] = f"{project_root}:{pythonpath}" if pythonpath else project_root

                    process = await asyncio.create_subprocess_exec(
                        sys.executable, str(self.WORKER_SCRIPT),
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=project_root,
                        env=env,
                    )

                    # Send input to the subprocess (non-blocking)
                    asyncio.create_task(self._feed_subprocess(process, worker_input, task_info.task_id))

                    start_time = asyncio.get_event_loop().time()
                    active_processes[task_info.task_id] = (process, start_time)
                    coordinator.update_task_status(task_info.task_id, TaskStatus.RUNNING)

            # Check for completed or timed out tasks
            completed_this_round = []
            current_time = asyncio.get_event_loop().time()

            for task_id, (process, start_time) in list(active_processes.items()):
                # Check for timeout
                elapsed = current_time - start_time
                if elapsed > self.TASK_TIMEOUT:
                    process.kill()
                    await process.wait()
                    coordinator.update_task_status(
                        task_id, TaskStatus.ERROR,
                        error=f"Task timed out after {self.TASK_TIMEOUT}s"
                    )
                    completed_this_round.append(task_id)
                    continue

                # Check if process has finished
                if process.returncode is not None:
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            process.communicate(),
                            timeout=5.0
                        )
                        stdout_text = stdout.decode('utf-8', errors='replace').strip()

                        if stdout_text:
                            task_result = json.loads(stdout_text)
                            if task_result.get("success"):
                                results[task_id] = task_result.get("result", "")
                                coordinator.update_task_status(
                                    task_id, TaskStatus.COMPLETED, output=task_result.get("result", "")
                                )
                            else:
                                coordinator.update_task_status(
                                    task_id, TaskStatus.ERROR, error=task_result.get("error", "Unknown error")
                                )
                        else:
                            stderr_text = stderr.decode('utf-8', errors='replace').strip()
                            coordinator.update_task_status(
                                task_id, TaskStatus.ERROR, error=f"No output from worker. stderr: {stderr_text[:500]}"
                            )
                    except json.JSONDecodeError as e:
                        coordinator.update_task_status(
                            task_id, TaskStatus.ERROR, error=f"Invalid JSON from worker: {str(e)}"
                        )
                    except asyncio.TimeoutError:
                        coordinator.update_task_status(
                            task_id, TaskStatus.ERROR, error="Timeout reading worker output"
                        )

                    completed_this_round.append(task_id)

            # Remove completed from tracking
            for task_id in completed_this_round:
                if task_id in active_processes:
                    process, _ = active_processes.pop(task_id)
                    # Ensure process is cleaned up
                    if process.returncode is None:
                        process.kill()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=2)
                        except asyncio.TimeoutError:
                            pass

            # If no tasks running and none ready, we might be stuck
            if not active_processes and not ready_tasks and not coordinator.all_tasks_complete():
                return "Error: Execution stalled - no tasks can proceed"

            # Small delay to prevent busy waiting
            if active_processes:
                await asyncio.sleep(0.5)

        # Clean up any remaining processes
        for task_id, (process, _) in list(active_processes.items()):
            if process.returncode is None:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except asyncio.TimeoutError:
                    pass

        # Build results summary
        return self._build_results_summary(coordinator, results)

    async def _feed_subprocess(self, process: asyncio.subprocess.Process, input_data: str, task_id: str) -> None:
        """Feed input to subprocess stdin."""
        try:
            if process.stdin:
                process.stdin.write(input_data.encode('utf-8'))
                await process.stdin.drain()
                process.stdin.close()
                await process.stdin.wait_closed()
        except Exception:
            pass  # Process may have already exited

    def _build_task_message(
        self, coordinator: ParallelCoordinator, task_info: SubTaskInfo
    ) -> str:
        """Build the message to send to the sub-agent."""

        # Include dependency outputs if any
        dep_outputs = ""
        if task_info.dependencies:
            dep_outputs = "\n\n**Outputs from dependency tasks:**\n"
            for dep_id in task_info.dependencies:
                dep_task = coordinator.get_task(dep_id)
                if dep_task and dep_task.output:
                    output = dep_task.output[:500]
                    if len(dep_task.output) > 500:
                        output += "..."
                    dep_outputs += f"\n### {dep_id}:\n{output}\n"

        workspace_note = ""
        if task_info.worktree_path:
            workspace_note = f"\n\n**IMPORTANT:** Work in worktree at: `{task_info.worktree_path}`\nUse `cd {task_info.worktree_path}` before any code operations."

        scratchpad_path = coordinator.scratchpad_path
        scratchpad_note = f"\n\n**Coordination scratchpad:** `{scratchpad_path}`\nCheck the scratchpad regularly for updates from peer agents working on related tasks."

        return f"""## Parallel Task Assignment

**Task ID:** {task_info.task_id}
**Description:** {task_info.description}
{workspace_note}
{dep_outputs}
{scratchpad_note}

Please complete this task. When finished, use the response tool to report your completion and any outputs that dependent tasks might need.
"""

    def _build_results_summary(
        self, coordinator: ParallelCoordinator, results: dict[str, str]
    ) -> str:
        """Build a summary of execution results."""

        lines = ["### Task Results\n"]

        for task_id, task in coordinator.state.tasks.items():
            status_icon = {
                TaskStatus.COMPLETED: "+",
                TaskStatus.ERROR: "x",
            }.get(task.status, "?")

            desc = task.description[:50]
            if len(task.description) > 50:
                desc += "..."

            lines.append(f"**{status_icon} {task_id}:** {desc}")

            if task.status == TaskStatus.COMPLETED and task.output:
                output = task.output[:200]
                if len(task.output) > 200:
                    output += "..."
                lines.append(f"   Output: {output}")
            elif task.status == TaskStatus.ERROR and task.error:
                lines.append(f"   Error: {task.error}")

            lines.append("")

        return "\n".join(lines)

    async def _merge_worktrees(
        self,
        coordinator: ParallelCoordinator,
        worktree_manager: GitWorktreeManager,
    ) -> str:
        """Merge all worktrees back to main branch."""

        lines = ["### Merge Results\n"]

        branches_to_merge = []
        for task in coordinator.state.tasks.values():
            if task.worktree_path:
                branch = f"{worktree_manager.BRANCH_PREFIX}/{coordinator.coordinator_id}/{task.task_id}"
                branches_to_merge.append((task.task_id, branch))

        for task_id, branch in branches_to_merge:
            result = worktree_manager.merge_worktree(
                branch,
                coordinator.state.main_branch,
                f"Merge parallel task {task_id}"
            )

            if result.success:
                lines.append(f"+ Merged `{task_id}` successfully")
            else:
                lines.append(f"x Failed to merge `{task_id}`: {result.message}")
                if result.conflicts:
                    lines.append(f"   Conflicts: {', '.join(result.conflicts)}")

        return "\n".join(lines)

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://account-group {self.agent.agent_name}: Parallel Task Delegation",
            content="",
            kvps=self.args,
        )
