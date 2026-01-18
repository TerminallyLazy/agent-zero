"""
Parallel Coordination System Prompt Extension

Injects parallel coordination context into subordinate agent prompts.
"""

from typing import Any
from python.helpers.extension import Extension
from agent import LoopData


class ParallelCoordinationPrompt(Extension):
    """Inject parallel coordination context for subordinate agents."""

    async def execute(
        self,
        system_prompt: list[str] = [],
        loop_data: LoopData = LoopData(),
        **kwargs: Any
    ):
        # Check if this agent is part of parallel coordination
        task_id = self.agent.get_data("_parallel_task_id")
        if not task_id:
            return  # Not a parallel subordinate

        coordinator = self.agent.get_data("_parallel_coordinator")
        worktree_path = self.agent.get_data("_parallel_worktree_path")

        if not coordinator:
            return

        # Get current scratchpad state
        scratchpad_summary = coordinator.get_scratchpad_summary()
        task_info = coordinator.get_task(task_id)

        if not task_info:
            return

        # Build coordination prompt
        deps_str = ", ".join(task_info.dependencies) if task_info.dependencies else "None"
        workspace_str = worktree_path or "No dedicated worktree"

        coordination_prompt = self.agent.read_prompt(
            "agent.system.parallel_subordinate.md",
            task_id=task_id,
            task_description=task_info.description,
            dependencies=deps_str,
            worktree_path=workspace_str,
            scratchpad_summary=scratchpad_summary,
        )

        if coordination_prompt:
            system_prompt.append(coordination_prompt)
