"""
Parallel Scratchpad Update Extension

After tool execution, update scratchpad with progress and file claims.
Tracks files modified by code execution commands.
"""

import re
from typing import Any
from python.helpers.extension import Extension
from python.helpers.parallel_coordinator import ParallelCoordinator
from python.helpers.tool import Response


class UpdateParallelScratchpad(Extension):
    """Update scratchpad after tool execution for parallel agents."""

    async def execute(
        self,
        tool_name: str = "",
        tool_args: dict[str, Any] = {},
        response: Response | None = None,
        **kwargs
    ) -> None:
        # Only applies to parallel subordinate agents
        coordinator: ParallelCoordinator | None = self.agent.get_data("_parallel_coordinator")
        task_id: str | None = self.agent.get_data("_parallel_task_id")

        if not coordinator or not task_id:
            return

        # Track file modifications from code execution
        if tool_name in ("code_execution", "code_execution_tool"):
            await self._track_file_modifications(coordinator, task_id, tool_args, response)

    async def _track_file_modifications(
        self,
        coordinator: ParallelCoordinator,
        task_id: str,
        tool_args: dict[str, Any],
        response: Response | None
    ) -> None:
        """Track files modified by code execution and claim them in the registry."""
        if not response:
            return

        # Get the command that was executed
        code = tool_args.get("code", "")
        runtime = tool_args.get("runtime", "")

        if runtime != "terminal":
            return

        # Check if command was successful (no error exit)
        response_lower = response.message.lower()
        if "error" in response_lower or "failed" in response_lower:
            return

        # Extract file paths from the command
        files_to_claim: set[str] = set()

        # Parse redirect operators: > file, >> file
        redirect_pattern = r'[>]{1,2}\s*([^\s;&|]+)'
        files_to_claim.update(re.findall(redirect_pattern, code))

        # Parse tee command: tee file, tee -a file
        tee_pattern = r'tee\s+(?:-[a-z]+\s+)?([^\s;&|]+)'
        files_to_claim.update(re.findall(tee_pattern, code))

        # Parse touch command: touch file1 file2
        if "touch " in code:
            touch_match = re.search(r'touch\s+(.+?)(?:;|&&|\|\||$)', code)
            if touch_match:
                # Split by spaces, filtering out flags
                parts = touch_match.group(1).split()
                files_to_claim.update(p for p in parts if not p.startswith("-"))

        # Parse cat heredoc: cat > file << EOF
        cat_heredoc_pattern = r'cat\s*>\s*([^\s<]+)'
        files_to_claim.update(re.findall(cat_heredoc_pattern, code))

        # Filter out special paths and claim files
        agent_name = self.agent.agent_name if hasattr(self.agent, 'agent_name') else f"agent_{task_id}"

        for file_path in files_to_claim:
            # Skip special paths
            if file_path in ("/dev/null", "-") or file_path.startswith("/dev/"):
                continue
            # Skip if looks like a flag
            if file_path.startswith("-"):
                continue

            # Attempt to claim the file (may already be claimed by this task)
            coordinator.claim_file(task_id, agent_name, file_path)
