"""
Tests for HGM utility functions

Tests the core HGM self-improvement utilities:
- choose_entry(): Strategy selection logic
- sample_child(): Child agent generation
- eval_agent(): Agent evaluation on tasks
- Metadata persistence
"""

import asyncio
import json
import os
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from python.helpers.hgm_utils import HGMUtils
from python.helpers.hgm_tree import TreeNode
from agent import Agent, AgentContext, AgentConfig
from python.helpers.tool import Response
import models


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing"""
    output_dir = tempfile.mkdtemp()
    git_dir = tempfile.mkdtemp()

    # Initialize git repo
    os.system(f'cd {git_dir} && git init && git config user.email "test@test.com" && git config user.name "Test"')
    os.system(f'cd {git_dir} && echo "initial" > file.txt && git add . && git commit -m "initial"')

    yield output_dir, git_dir

    # Cleanup
    shutil.rmtree(output_dir)
    shutil.rmtree(git_dir)


@pytest.fixture
def agent():
    """Create mock agent"""
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
    agent.set_data('hgm_nodes', {})

    return agent


@pytest.fixture
def hgm_utils(agent, temp_dirs):
    """Create HGMUtils instance"""
    output_dir, git_dir = temp_dirs
    return HGMUtils(
        agent=agent,
        output_dir=output_dir,
        git_dir=git_dir,
        base_commit="HEAD",
        total_tasks=["task1", "task2", "task3", "task4", "task5"]
    )


class TestChooseEntry:
    """Test strategy selection logic"""

    def test_empty_patches_strategy(self, hgm_utils):
        """Test selection of empty_patches strategy when ratio is high"""
        # Create metadata with 15% empty patches
        metadata = {
            'resolved_ids': ['t1', 't2'],
            'unresolved_ids': ['t3', 't4', 't5'],
            'empty_patch_ids': ['t6', 't7'],  # 2/7 = 28% empty
            'evaluated_tasks': {}
        }

        # Run multiple times to hit the 25% probability
        strategies = set()
        for _ in range(50):
            strategy = hgm_utils.choose_entry(metadata)
            strategies.add(strategy)

        # Should include solve_empty_patches due to high ratio
        assert 'solve_empty_patches' in strategies or any(
            s in metadata['unresolved_ids'] for s in strategies
        )

    def test_stochasticity_strategy(self, hgm_utils):
        """Test selection of stochasticity strategy"""
        metadata = {
            'resolved_ids': ['t1', 't2', 't3'],
            'unresolved_ids': ['t4', 't5'],
            'empty_patch_ids': [],  # Low empty ratio
            'evaluated_tasks': {}
        }

        # Run multiple times to hit stochasticity probability
        strategies = set()
        for _ in range(50):
            strategy = hgm_utils.choose_entry(metadata)
            strategies.add(strategy)

        # Should include solve_stochasticity or unresolved tasks
        assert 'solve_stochasticity' in strategies or any(
            s in metadata['unresolved_ids'] for s in strategies
        )

    def test_context_length_strategy(self, hgm_utils):
        """Test selection of context length strategy when errors exist"""
        metadata = {
            'resolved_ids': ['t1'],
            'unresolved_ids': ['t2', 't3'],
            'empty_patch_ids': [],
            'context_length_errors': ['t2'],  # Has context errors
            'evaluated_tasks': {}
        }

        # Run multiple times
        strategies = set()
        for _ in range(50):
            strategy = hgm_utils.choose_entry(metadata)
            strategies.add(strategy)

        # Should potentially include solve_contextlength
        assert any(s in [
            'solve_contextlength',
            'solve_stochasticity',
            't2', 't3'
        ] for s in strategies)

    def test_unresolved_task_selection(self, hgm_utils):
        """Test default selection of unresolved tasks"""
        metadata = {
            'resolved_ids': ['t1', 't2'],
            'unresolved_ids': ['t3', 't4', 't5'],
            'empty_patch_ids': [],
            'evaluated_tasks': {}
        }

        # Run multiple times
        selections = []
        for _ in range(20):
            strategy = hgm_utils.choose_entry(metadata)
            selections.append(strategy)

        # Should select from unresolved or strategy names
        valid_selections = metadata['unresolved_ids'] + [
            'solve_empty_patches',
            'solve_stochasticity',
            'solve_contextlength'
        ]

        assert all(s in valid_selections for s in selections)

    def test_initial_evaluation(self, hgm_utils):
        """Test initial evaluation when no metadata exists"""
        metadata = {
            'resolved_ids': [],
            'unresolved_ids': [],
            'empty_patch_ids': [],
            'evaluated_tasks': {}
        }

        strategy = hgm_utils.choose_entry(metadata)
        assert strategy == "initial_evaluation"


class TestMetadataPersistence:
    """Test metadata save/load operations"""

    def test_save_and_load_metadata(self, hgm_utils):
        """Test saving and loading node metadata"""
        node = TreeNode(commit_id="abc123", parent_id=None, node_id=0)

        metadata = {
            'accuracy': 0.75,
            'resolved_ids': ['t1', 't2', 't3'],
            'unresolved_ids': ['t4']
        }

        # Save metadata
        hgm_utils.save_node_metadata(node, metadata)

        # Load metadata
        loaded = hgm_utils.load_node_metadata(node)

        assert loaded is not None
        assert loaded['accuracy'] == 0.75
        assert loaded['resolved_ids'] == ['t1', 't2', 't3']
        assert loaded['unresolved_ids'] == ['t4']

    def test_load_nonexistent_metadata(self, hgm_utils):
        """Test loading metadata for node without metadata file"""
        node = TreeNode(commit_id="nonexistent", parent_id=None, node_id=999)

        loaded = hgm_utils.load_node_metadata(node)
        assert loaded is None

    def test_metadata_merge_on_save(self, hgm_utils):
        """Test that saving metadata merges with existing data"""
        node = TreeNode(commit_id="merge123", parent_id=None, node_id=0)

        # Save initial metadata
        initial = {'accuracy': 0.5, 'resolved_ids': ['t1']}
        hgm_utils.save_node_metadata(node, initial)

        # Save additional metadata
        additional = {'unresolved_ids': ['t2', 't3']}
        hgm_utils.save_node_metadata(node, additional)

        # Load and verify merge
        loaded = hgm_utils.load_node_metadata(node)
        assert loaded['accuracy'] == 0.5
        assert loaded['resolved_ids'] == ['t1']
        assert loaded['unresolved_ids'] == ['t2', 't3']


@pytest.mark.asyncio
class TestEvalAgent:
    """Test agent evaluation"""

    async def test_eval_failed_agent(self, hgm_utils):
        """Test evaluation of failed agent returns zeros"""
        node = TreeNode(commit_id="failed", parent_id=None, node_id=0)

        results = await hgm_utils.eval_agent(node, num_tasks=3)

        assert results == [0, 0, 0]

    async def test_eval_agent_random_task_selection(self, hgm_utils):
        """Test that eval_agent selects random tasks when not specified"""
        node = TreeNode(commit_id="test_commit", parent_id=None, node_id=0)

        # Create metadata with some evaluated tasks
        metadata = {
            'commit_id': 'test_commit',
            'node_id': 0,
            'evaluated_tasks': {'task1': 1, 'task2': 0},
            'resolved_ids': ['task1'],
            'unresolved_ids': ['task2'],
            'empty_patch_ids': []
        }

        hgm_utils.save_node_metadata(node, metadata)

        # Mock RepoSolver to return success
        with patch('python.tools.repo_solver_tool.RepoSolver') as mock_solver_class:
            mock_solver = MagicMock()
            mock_solver.execute = AsyncMock(return_value=Response(
                message="success",
                break_loop=False
            ))
            mock_solver_class.return_value = mock_solver

            # Evaluate 2 tasks
            results = await hgm_utils.eval_agent(node, num_tasks=2)

            # Should have 2 results
            assert len(results) == 2

    async def test_eval_agent_specific_tasks(self, hgm_utils):
        """Test evaluation on specific tasks"""
        node = TreeNode(commit_id="test_commit", parent_id=None, node_id=0)

        # Mock RepoSolver
        with patch('python.tools.repo_solver_tool.RepoSolver') as mock_solver_class:
            mock_solver = MagicMock()
            mock_solver.execute = AsyncMock(return_value=Response(
                message="success",
                break_loop=False
            ))
            mock_solver_class.return_value = mock_solver

            # Evaluate specific tasks
            results = await hgm_utils.eval_agent(node, tasks=['task3', 'task4'])

            assert len(results) == 2


@pytest.mark.asyncio
class TestSampleChild:
    """Test child agent generation"""

    async def test_sample_child_from_failed_parent(self, hgm_utils):
        """Test that sampling from failed parent returns None"""
        parent_node = TreeNode(commit_id="failed", parent_id=None, node_id=0)

        result = await hgm_utils.sample_child(parent_node)

        assert result == (None, None)

    async def test_sample_child_missing_parent_metadata(self, hgm_utils, temp_dirs):
        """Test handling of missing parent metadata"""
        _, git_dir = temp_dirs

        # Get initial commit
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=git_dir,
            capture_output=True,
            text=True
        )
        commit_id = result.stdout.strip()

        parent_node = TreeNode(commit_id=commit_id, parent_id=None, node_id=0)

        result = await hgm_utils.sample_child(parent_node)

        # Should return None due to missing metadata
        assert result == (None, None)

    async def test_sample_child_success(self, hgm_utils, temp_dirs):
        """Test successful child generation calls diagnostic and delegation properly"""
        _, git_dir = temp_dirs

        # Get initial commit
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=git_dir,
            capture_output=True,
            text=True
        )
        commit_id = result.stdout.strip()

        parent_node = TreeNode(commit_id=commit_id, parent_id=None, node_id=0)

        # Create parent metadata
        parent_metadata = {
            'commit_id': commit_id,
            'node_id': 0,
            'resolved_ids': ['t1'],
            'unresolved_ids': ['t2', 't3'],
            'empty_patch_ids': [],
            'logs': 'Test logs',
            'last_patch': 'diff --git...',
            'test_results': 'Tests passed: 1/3'
        }

        hgm_utils.save_node_metadata(parent_node, parent_metadata)

        # Mock diagnostic tool
        with patch('python.tools.diagnostic_tool.Diagnostic') as mock_diag_class:
            mock_diag = MagicMock()
            mock_diag.execute = AsyncMock(return_value=Response(
                message="Improvement suggestions: Fix error handling",
                break_loop=False
            ))
            mock_diag_class.return_value = mock_diag

            # Mock subprocess.run to simulate commit being made by subordinate
            with patch('subprocess.run') as mock_subprocess:
                # First call: git reset (return success)
                # Second call: git rev-parse HEAD (return new commit)
                mock_subprocess.side_effect = [
                    MagicMock(returncode=0, stdout='', stderr=''),  # git reset
                    MagicMock(returncode=0, stdout='new_commit_abc123', stderr='', strip=lambda: 'new_commit_abc123'),  # git rev-parse
                ]

                # Also need to mock the subprocess.run calls inside sample_child
                # to return different commit IDs
                def mock_run_side_effect(*args, **kwargs):
                    if 'rev-parse' in args[0]:
                        result = MagicMock()
                        result.stdout = 'new_commit_abc123'
                        result.strip = lambda: 'new_commit_abc123'
                        return result
                    else:
                        result = MagicMock()
                        result.returncode = 0
                        result.stdout = ''
                        result.stderr = ''
                        return result

                mock_subprocess.side_effect = mock_run_side_effect

                # Mock subordinate agent (Delegation)
                with patch('python.tools.call_subordinate.Delegation') as mock_delegation_class:
                    mock_delegation = MagicMock()
                    mock_delegation.execute = AsyncMock(return_value=Response(
                        message="Implemented improvements",
                        break_loop=False
                    ))
                    mock_delegation_class.return_value = mock_delegation

                    # Sample child
                    new_commit, child_node_id = await hgm_utils.sample_child(parent_node)

                    # Should have called diagnostic tool
                    assert mock_diag_class.called
                    # Should have called delegation
                    assert mock_delegation_class.called

                    # Should return new commit and node ID
                    assert new_commit == 'new_commit_abc123'
                    assert child_node_id is not None


def test_strategy_to_analysis_type(hgm_utils):
    """Test strategy to analysis type conversion"""
    assert hgm_utils._strategy_to_analysis_type("solve_empty_patches") == "empty_patch"
    assert hgm_utils._strategy_to_analysis_type("solve_stochasticity") == "stochasticity"
    assert hgm_utils._strategy_to_analysis_type("solve_contextlength") == "failure_analysis"
    assert hgm_utils._strategy_to_analysis_type("task123") == "failure_analysis"
