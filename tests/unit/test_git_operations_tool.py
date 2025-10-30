# tests/unit/test_git_operations_tool.py
import pytest
import os
import tempfile
import subprocess
from agent import Agent, AgentContext, AgentConfig
from python.tools.git_operations_tool import GitOperations
import models

@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=tmpdir, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=tmpdir, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=tmpdir, check=True)

        # Create initial commit
        test_file = os.path.join(tmpdir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('initial content\n')
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, check=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=tmpdir, check=True)

        # Get the commit hash
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=True
        )
        base_commit = result.stdout.strip()

        # Make a change
        with open(test_file, 'w') as f:
            f.write('modified content\n')

        yield tmpdir, base_commit

@pytest.fixture
def agent_setup():
    """Create agent with minimal configuration for testing"""
    # Create minimal model configs for testing
    model_config = models.ModelConfig(
        type=models.ModelType.CHAT,
        provider="openai",
        name="gpt-4",
    )

    config = AgentConfig(
        chat_model=model_config,
        utility_model=model_config,
        embeddings_model=model_config,
        browser_model=model_config,
        mcp_servers="",
    )
    context = AgentContext(config)
    agent = Agent(0, config, context)
    return agent

@pytest.mark.asyncio
async def test_diff_versus_commit(temp_git_repo, agent_setup):
    """Verify diff generation against base commit"""
    git_dir, base_commit = temp_git_repo
    agent = agent_setup

    # Create tool instance
    tool = GitOperations(
        agent=agent,
        name="git_operations_tool",
        method=None,
        args={
            'operation': 'diff',
            'git_dir': git_dir,
            'base_commit': base_commit
        },
        message="",
        loop_data=None
    )

    # Execute
    response = await tool.execute()

    # Assert: Valid unified diff format returned
    assert response.message is not None
    assert 'diff --git' in response.message
    assert '-initial content' in response.message
    assert '+modified content' in response.message

@pytest.mark.asyncio
async def test_apply_patch(temp_git_repo, agent_setup):
    """Verify patch application to repository"""
    git_dir, base_commit = temp_git_repo
    agent = agent_setup

    # Generate a patch
    patch_content = """diff --git a/test.txt b/test.txt
index 1234567..abcdefg 100644
--- a/test.txt
+++ b/test.txt
@@ -1 +1 @@
-modified content
+patched content
"""

    # Apply patch
    tool = GitOperations(
        agent=agent,
        name="git_operations_tool",
        method=None,
        args={
            'operation': 'apply_patch',
            'git_dir': git_dir,
            'patch_content': patch_content
        },
        message="",
        loop_data=None
    )

    response = await tool.execute()

    # Verify patch was applied
    test_file = os.path.join(git_dir, 'test.txt')
    with open(test_file, 'r') as f:
        content = f.read()

    assert 'patched content' in content

@pytest.mark.asyncio
async def test_reset_to_commit(temp_git_repo, agent_setup):
    """Verify repository reset to specific commit"""
    git_dir, base_commit = temp_git_repo
    agent = agent_setup

    # Commit the current changes
    subprocess.run(['git', 'add', '.'], cwd=git_dir, check=True)
    subprocess.run(['git', 'commit', '-m', 'Second commit'], cwd=git_dir, check=True)

    # Reset to base commit
    tool = GitOperations(
        agent=agent,
        name="git_operations_tool",
        method=None,
        args={
            'operation': 'reset',
            'git_dir': git_dir,
            'target_commit': base_commit,
            'hard': True
        },
        message="",
        loop_data=None
    )

    response = await tool.execute()

    # Verify reset worked
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=git_dir,
        capture_output=True,
        text=True,
        check=True
    )
    current_commit = result.stdout.strip()

    assert current_commit == base_commit
