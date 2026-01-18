"""
Parallel Scratchpad Check Extension

Before tool execution, check scratchpad for updates and file conflicts.
Blocks conflicting file modifications by replacing the command with an error.
"""

from typing import Any
from python.helpers.extension import Extension
from python.helpers.parallel_coordinator import ParallelCoordinator


class CheckParallelScratchpad(Extension):
    """Check scratchpad state before tool execution for parallel agents."""

    async def execute(self, tool_name: str = "", tool_args: dict[str, Any] = {}, **kwargs) -> None:
        # Only applies to parallel subordinate agents
        coordinator: ParallelCoordinator | None = self.agent.get_data("_parallel_coordinator")
        task_id: str | None = self.agent.get_data("_parallel_task_id")

        if not coordinator or not task_id:
            return

        # Skip for non-file-modifying tools
        if tool_name not in ("code_execution", "code_execution_tool"):
            return

        # Check if code execution is modifying files
        code = tool_args.get("code", "")
        runtime = tool_args.get("runtime", "")

        if runtime != "terminal":
            return

        # Detect file-modifying commands
        file_modifying_patterns = [
            " > ", " >> ",  # Shell redirects
            "touch ", "mkdir -p", "rm ",  # File operations
            "mv ", "cp ",  # Move/copy
            "sed -i", "awk ",  # In-place edits
            "git add", "git commit",  # Git operations
            "cat >", "tee ",  # Write operations
        ]

        is_modifying = any(pattern in code for pattern in file_modifying_patterns)

        if not is_modifying:
            return

        # Extract potential file paths from command (basic heuristic)
        conflicts_found: list[tuple[str, str]] = []  # (file_path, blocking_task)
        parts = code.split()

        for i, part in enumerate(parts):
            # Check redirect operators
            if part in (">", ">>") and i + 1 < len(parts):
                file_path = parts[i + 1]
                conflict = coordinator.check_file_conflict(task_id, file_path)
                if conflict:
                    conflicts_found.append((file_path, conflict))

            # Check tee command
            if part == "tee" and i + 1 < len(parts):
                file_path = parts[i + 1]
                if not file_path.startswith("-"):  # Skip flags
                    conflict = coordinator.check_file_conflict(task_id, file_path)
                    if conflict:
                        conflicts_found.append((file_path, conflict))

        if conflicts_found:
            # Block the command by replacing it with an error message
            conflict_details = ", ".join(
                f"'{fp}' (blocked by task {bt})" for fp, bt in conflicts_found
            )
            error_msg = (
                f"PARALLEL EXECUTION BLOCKED: File conflict detected. "
                f"The following files are being modified by other parallel tasks: {conflict_details}. "
                f"Wait for those tasks to complete or choose different files."
            )

            # Replace the original command with an echo that reports the conflict
            # This ensures the tool "executes" but produces an error the agent will see
            tool_args["code"] = f'echo "ERROR: {error_msg}" >&2 && exit 1'

            # Also store for agent reference
            self.agent.set_data("_parallel_file_conflict_warning", error_msg)
