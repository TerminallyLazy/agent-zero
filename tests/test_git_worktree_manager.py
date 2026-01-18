# tests/test_git_worktree_manager.py
import pytest
from python.helpers.git_worktree_manager import GitWorktreeManager

def test_worktree_manager_exists():
    """Test that GitWorktreeManager class exists."""
    assert GitWorktreeManager is not None
