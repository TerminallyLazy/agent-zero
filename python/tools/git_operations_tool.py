# python/tools/git_operations_tool.py
from python.helpers.tool import Tool, Response
import os
import subprocess
import tempfile

class GitOperations(Tool):
    """
    Tool for performing git operations on repositories.

    This tool uses subprocess to execute git commands directly rather than CodeExecution
    because:
    1. Better for unit testing - subprocess calls can be easily mocked
    2. Stateless operations - no session state to manage
    3. More direct control - immediate feedback without terminal session overhead
    4. Simpler error handling - direct capture of stdout/stderr

    Operations:
    - diff: Generate diff against a base commit
    - apply_patch: Apply a patch file to repository
    - reset: Reset repository to a specific commit
    - get_log: Get commit log
    """

    async def execute(self, **kwargs) -> Response:
        await self.agent.handle_intervention()

        operation = self.args.get('operation', '').lower()
        git_dir = self.args.get('git_dir', '')

        if not git_dir:
            return Response(
                message=self.agent.read_prompt(
                    "agent.system.tool.git_operations.md",
                    error="git_dir is required"
                ),
                break_loop=False
            )

        if not os.path.exists(git_dir):
            return Response(
                message=f"Error: Directory {git_dir} does not exist",
                break_loop=False
            )

        if operation == 'diff':
            return await self._diff(git_dir)
        elif operation == 'apply_patch':
            return await self._apply_patch(git_dir)
        elif operation == 'reset':
            return await self._reset(git_dir)
        elif operation == 'get_log':
            return await self._get_log(git_dir)
        else:
            return Response(
                message=f"Error: Unknown operation '{operation}'",
                break_loop=False
            )

    async def _diff(self, git_dir: str) -> Response:
        """Generate diff against base commit"""
        base_commit = self.args.get('base_commit', 'HEAD')

        try:
            result = subprocess.run(
                ['git', 'diff', base_commit],
                cwd=git_dir,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0 and result.stderr:
                return Response(
                    message=f"Error running git diff: {result.stderr}",
                    break_loop=False
                )

            return Response(
                message=result.stdout,
                break_loop=False
            )
        except Exception as e:
            return Response(
                message=f"Error executing git diff: {str(e)}",
                break_loop=False
            )

    async def _apply_patch(self, git_dir: str) -> Response:
        """Apply a patch to the repository"""
        patch_content = self.args.get('patch_content', '')

        if not patch_content:
            return Response(
                message="Error: patch_content is required for apply_patch operation",
                break_loop=False
            )

        # Write patch to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
            f.write(patch_content)
            patch_file = f.name

        try:
            # Apply patch using git apply
            result = subprocess.run(
                ['git', 'apply', patch_file],
                cwd=git_dir,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                return Response(
                    message=f"Error applying patch: {result.stderr}",
                    break_loop=False
                )

            return Response(
                message=f"Patch applied successfully\n{result.stdout}",
                break_loop=False
            )
        except Exception as e:
            return Response(
                message=f"Error executing git apply: {str(e)}",
                break_loop=False
            )
        finally:
            # Clean up temp file
            if os.path.exists(patch_file):
                os.unlink(patch_file)

    async def _reset(self, git_dir: str) -> Response:
        """Reset repository to specific commit"""
        target_commit = self.args.get('target_commit', 'HEAD')
        hard = self.args.get('hard', False)

        reset_type = '--hard' if hard else '--soft'

        try:
            result = subprocess.run(
                ['git', 'reset', reset_type, target_commit],
                cwd=git_dir,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                return Response(
                    message=f"Error resetting repository: {result.stderr}",
                    break_loop=False
                )

            return Response(
                message=f"Repository reset successfully\n{result.stdout}",
                break_loop=False
            )
        except Exception as e:
            return Response(
                message=f"Error executing git reset: {str(e)}",
                break_loop=False
            )

    async def _get_log(self, git_dir: str) -> Response:
        """Get commit log"""
        limit = self.args.get('limit', 10)

        try:
            result = subprocess.run(
                ['git', 'log', '-n', str(limit), '--oneline'],
                cwd=git_dir,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                return Response(
                    message=f"Error getting git log: {result.stderr}",
                    break_loop=False
                )

            return Response(
                message=result.stdout,
                break_loop=False
            )
        except Exception as e:
            return Response(
                message=f"Error executing git log: {str(e)}",
                break_loop=False
            )

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://source_control Git Operations: {self.args.get('operation', 'unknown')}",
            content="",
            kvps=self.args,
        )
