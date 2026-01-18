"""
Git Worktree Manager Helper

Manages git worktree operations for isolated parallel agent workspaces.
Provides:
- Worktree creation with automatic branch management
- Worktree listing and cleanup
- Merge operations with conflict detection
- Merge preview (dry run)
"""

import os
import subprocess
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent import Agent


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""
    path: str
    branch: str
    commit: str
    is_detached: bool = False


@dataclass
class MergeResult:
    """Result of a merge operation."""
    success: bool
    merged_branch: str
    conflicts: list[str]
    message: str


@dataclass
class ConflictInfo:
    """Information about a potential merge conflict."""
    file_path: str
    branches: list[str]
    conflict_type: str  # "content" | "add/add" | "modify/delete"


class GitWorktreeManager:
    """
    Manages git worktrees for parallel agent workspaces.

    Worktrees are created in {project}/.worktrees/{task_id}/
    Each worktree gets a dedicated branch: parallel/{coordinator_id}/{task_id}
    """

    WORKTREE_DIR = ".worktrees"
    BRANCH_PREFIX = "parallel"

    def __init__(self, project_path: str, coordinator_id: str):
        self.project_path = project_path
        self.coordinator_id = coordinator_id
        self.worktrees_base = os.path.join(project_path, self.WORKTREE_DIR)

    def _run_git(
        self, args: list[str], cwd: Optional[str] = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a git command and return the result."""
        cmd = ["git"] + args
        result = subprocess.run(
            cmd,
            cwd=cwd or self.project_path,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{result.stderr}")
        return result

    def ensure_repo_initialized(self) -> str:
        """
        Ensure the project has a git repository.
        Returns the main branch name.
        """
        git_dir = os.path.join(self.project_path, ".git")

        if not os.path.exists(git_dir):
            # Initialize new repo
            self._run_git(["init"])
            self._run_git(["add", "."])
            self._run_git(["commit", "-m", "Initial commit for parallel execution"])

        # Get main branch name
        result = self._run_git(["branch", "--show-current"])
        main_branch = result.stdout.strip()

        if not main_branch:
            # Might be detached HEAD, try to get default
            result = self._run_git(["config", "--get", "init.defaultBranch"], check=False)
            main_branch = result.stdout.strip() or "main"

        return main_branch

    def create_worktree(self, task_id: str, base_branch: str = "HEAD") -> str:
        """
        Create a new worktree for a task.

        Args:
            task_id: Unique identifier for the task
            base_branch: Branch to base the worktree on (default: HEAD)

        Returns:
            Path to the created worktree
        """
        # Create worktrees directory if needed
        os.makedirs(self.worktrees_base, exist_ok=True)

        # Generate branch and path names
        branch_name = f"{self.BRANCH_PREFIX}/{self.coordinator_id}/{task_id}"
        worktree_path = os.path.join(self.worktrees_base, task_id)

        # Remove existing worktree if present
        if os.path.exists(worktree_path):
            self.remove_worktree(worktree_path, force=True)

        # Delete branch if it exists
        self._run_git(["branch", "-D", branch_name], check=False)

        # Create worktree with new branch
        self._run_git(["worktree", "add", "-b", branch_name, worktree_path, base_branch])

        return worktree_path

    def list_worktrees(self) -> list[WorktreeInfo]:
        """List all worktrees in the repository."""
        result = self._run_git(["worktree", "list", "--porcelain"])

        worktrees = []
        current = {}

        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line:
                if current.get("path"):
                    worktrees.append(WorktreeInfo(
                        path=current.get("path", ""),
                        branch=current.get("branch", "").replace("refs/heads/", ""),
                        commit=current.get("HEAD", ""),
                        is_detached=current.get("detached", False),
                    ))
                current = {}
            elif line.startswith("worktree "):
                current["path"] = line[9:]
            elif line.startswith("HEAD "):
                current["HEAD"] = line[5:]
            elif line.startswith("branch "):
                current["branch"] = line[7:]
            elif line == "detached":
                current["detached"] = True

        # Handle last entry
        if current.get("path"):
            worktrees.append(WorktreeInfo(
                path=current.get("path", ""),
                branch=current.get("branch", "").replace("refs/heads/", ""),
                commit=current.get("HEAD", ""),
                is_detached=current.get("detached", False),
            ))

        return worktrees

    def get_coordinator_worktrees(self) -> list[WorktreeInfo]:
        """Get worktrees belonging to this coordinator."""
        prefix = f"{self.BRANCH_PREFIX}/{self.coordinator_id}/"
        return [
            wt for wt in self.list_worktrees()
            if wt.branch.startswith(prefix)
        ]

    def remove_worktree(self, worktree_path: str, force: bool = False) -> None:
        """Remove a worktree."""
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(worktree_path)

        self._run_git(args, check=False)

    def remove_branch(self, branch_name: str, force: bool = False) -> None:
        """Remove a branch."""
        flag = "-D" if force else "-d"
        self._run_git(["branch", flag, branch_name], check=False)

    def merge_worktree(
        self, branch_name: str, target_branch: str = "main", message: Optional[str] = None
    ) -> MergeResult:
        """
        Merge a worktree branch into target branch.

        Args:
            branch_name: Branch to merge
            target_branch: Target branch (default: main)
            message: Custom merge commit message

        Returns:
            MergeResult with success status and any conflicts
        """
        # Checkout target branch in main worktree
        self._run_git(["checkout", target_branch])

        # Attempt merge
        merge_msg = message or f"Merge {branch_name} from parallel execution"
        result = self._run_git(
            ["merge", branch_name, "-m", merge_msg],
            check=False
        )

        if result.returncode == 0:
            return MergeResult(
                success=True,
                merged_branch=branch_name,
                conflicts=[],
                message="Merge successful",
            )

        # Check for conflicts
        status_result = self._run_git(["status", "--porcelain"])
        conflicts = []
        for line in status_result.stdout.split("\n"):
            if line.startswith("UU ") or line.startswith("AA "):
                conflicts.append(line[3:])

        if conflicts:
            # Abort merge to leave repo clean
            self._run_git(["merge", "--abort"], check=False)
            return MergeResult(
                success=False,
                merged_branch=branch_name,
                conflicts=conflicts,
                message=f"Merge conflicts in: {', '.join(conflicts)}",
            )

        return MergeResult(
            success=False,
            merged_branch=branch_name,
            conflicts=[],
            message=f"Merge failed: {result.stderr}",
        )

    def detect_potential_conflicts(self, branches: list[str]) -> list[ConflictInfo]:
        """
        Detect potential merge conflicts between branches without actually merging.
        Uses git merge-tree for dry-run analysis.
        """
        if len(branches) < 2:
            return []

        conflicts = []
        base_branch = branches[0]

        for branch in branches[1:]:
            # Get merge base
            base_result = self._run_git(
                ["merge-base", base_branch, branch],
                check=False
            )
            if base_result.returncode != 0:
                continue

            merge_base = base_result.stdout.strip()

            # Use merge-tree to check for conflicts
            result = self._run_git(
                ["merge-tree", merge_base, base_branch, branch],
                check=False
            )

            # Parse output for conflicts
            for line in result.stdout.split("\n"):
                if "+" in line and line.count("+") == 2:
                    # Potential conflict indicator
                    parts = line.split()
                    if len(parts) >= 3:
                        file_path = parts[-1]
                        conflicts.append(ConflictInfo(
                            file_path=file_path,
                            branches=[base_branch, branch],
                            conflict_type="content",
                        ))

        return conflicts

    def create_merge_preview(self, branches: list[str], target_branch: str = "main") -> str:
        """
        Create a preview of what merging all branches would look like.
        Returns a human-readable report.
        """
        lines = [f"## Merge Preview for {len(branches)} branches into {target_branch}\n"]

        # Check for potential conflicts
        all_branches = [target_branch] + branches
        conflicts = self.detect_potential_conflicts(all_branches)

        if conflicts:
            lines.append("### Warning: Potential Conflicts Detected\n")
            for conflict in conflicts:
                lines.append(f"- **{conflict.file_path}**: between {' and '.join(conflict.branches)}")
            lines.append("")
        else:
            lines.append("### No Conflicts Detected\n")
            lines.append("All branches appear to merge cleanly.\n")

        # List changes per branch
        lines.append("### Changes by Branch\n")
        for branch in branches:
            lines.append(f"**{branch}:**")

            # Get commits unique to this branch
            result = self._run_git(
                ["log", f"{target_branch}..{branch}", "--oneline"],
                check=False
            )

            if result.stdout.strip():
                for commit in result.stdout.strip().split("\n")[:5]:
                    lines.append(f"  - {commit}")
                commit_count = len(result.stdout.strip().split("\n"))
                if commit_count > 5:
                    lines.append(f"  - ... and {commit_count - 5} more commits")
            else:
                lines.append("  - No new commits")

            lines.append("")

        return "\n".join(lines)

    def cleanup_coordinator_worktrees(self, delete_branches: bool = True) -> None:
        """Remove all worktrees and optionally branches for this coordinator."""
        worktrees = self.get_coordinator_worktrees()

        for wt in worktrees:
            self.remove_worktree(wt.path, force=True)
            if delete_branches and wt.branch:
                self.remove_branch(wt.branch, force=True)

        # Clean up worktrees directory if empty
        if os.path.exists(self.worktrees_base):
            try:
                remaining = os.listdir(self.worktrees_base)
                if not remaining:
                    os.rmdir(self.worktrees_base)
            except OSError:
                pass  # Directory not empty, that's fine
