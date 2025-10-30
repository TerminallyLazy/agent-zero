# tests/unit/test_hgm_self_improve_tool.py
import pytest
import os
import tempfile
import json
from agent import Agent, AgentContext, AgentConfig
from python.tools.hgm_self_improve_tool import HGMSelfImprove
import models

@pytest.fixture
def temp_output_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

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
async def test_initialize_creates_root(agent_setup, temp_output_dir):
    """Verify initialization creates root node"""
    agent = agent_setup

    # Initialize HGM system
    tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve_tool",
        method=None,
        args={
            'operation': 'initialize',
            'output_dir': temp_output_dir,
            'agent_profile': 'default',
            'config': {
                'max_task_evals': 100,
                'max_workers': 1,
                'alpha': 0.5,
                'beta': 1.0
            }
        },
        message="",
        loop_data=None
    )

    response = await tool.execute()

    # Check response
    assert response.message is not None
    assert 'initialized' in response.message.lower()

    # Check metadata file was created
    metadata_file = os.path.join(temp_output_dir, 'hgm_metadata.json')
    assert os.path.exists(metadata_file)

    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    assert 'root_node' in metadata
    assert metadata['root_node']['node_id'] == 0

    # Check agent data has root node
    nodes = agent.get_data('hgm_nodes')
    assert nodes is not None
    assert 0 in nodes


# Tests for _run() orchestration loop


@pytest.mark.asyncio
async def test_run_decision_expands_when_threshold_met(agent_setup, temp_output_dir, monkeypatch):
    """Test that _run() calls _expand() when decision rule favors expansion"""
    from unittest.mock import AsyncMock, MagicMock, patch
    from python.helpers.hgm_tree import TreeNode

    agent = agent_setup

    # Set up agent data to favor expansion
    # Decision rule: n_task_evals**alpha >= len(nodes) - 1 + n_pending_expands
    # With alpha=0.5, n_task_evals=4: 4**0.5 = 2.0
    # With 2 nodes: 2 - 1 + 0 = 1
    # 2.0 >= 1.0, so should expand
    root_node = TreeNode(commit_id="abc123", parent_id=None, node_id=0)
    child_node = TreeNode(commit_id="def456", parent_id="abc123", node_id=1)

    agent.set_data('hgm_nodes', {0: root_node, 1: child_node})
    agent.set_data('hgm_n_task_evals', 4)
    agent.set_data('hgm_n_pending_expands', 0)
    agent.set_data('hgm_output_dir', temp_output_dir)
    agent.set_data('hgm_alpha', 0.5)
    agent.set_data('hgm_total_tasks', ['task1', 'task2', 'task3'])

    # Mock _expand and _evaluate methods
    expand_called = False
    evaluate_called = False

    async def mock_expand(self):
        nonlocal expand_called
        expand_called = True
        from python.helpers.tool import Response
        return Response(message="Expanded successfully", break_loop=False)

    async def mock_evaluate(self):
        nonlocal evaluate_called
        evaluate_called = True
        from python.helpers.tool import Response
        return Response(message="Evaluated successfully", break_loop=False)

    # Patch the methods
    with patch.object(HGMSelfImprove, '_expand', new=mock_expand):
        with patch.object(HGMSelfImprove, '_evaluate', new=mock_evaluate):
            tool = HGMSelfImprove(
                agent=agent,
                name="hgm_self_improve_tool",
                method=None,
                args={
                    'operation': 'run',
                    'iterations': 1
                },
                message="",
                loop_data=None
            )

            response = await tool.execute()

    # Verify _expand was called, not _evaluate
    assert expand_called
    assert not evaluate_called
    assert 'expand: 1' in response.message.lower()


@pytest.mark.asyncio
async def test_run_decision_evaluates_when_threshold_not_met(agent_setup, temp_output_dir, monkeypatch):
    """Test that _run() calls _evaluate() when decision rule favors evaluation"""
    from unittest.mock import AsyncMock, MagicMock, patch
    from python.helpers.hgm_tree import TreeNode

    agent = agent_setup

    # Set up agent data to favor evaluation
    # Decision rule: n_task_evals**alpha >= len(nodes) - 1 + n_pending_expands
    # With alpha=0.5, n_task_evals=1: 1**0.5 = 1.0
    # With 5 nodes: 5 - 1 + 0 = 4
    # 1.0 < 4.0, so should evaluate
    nodes = {i: TreeNode(commit_id=f"commit{i}", parent_id=f"commit{i-1}" if i > 0 else None, node_id=i) for i in range(5)}

    agent.set_data('hgm_nodes', nodes)
    agent.set_data('hgm_n_task_evals', 1)
    agent.set_data('hgm_n_pending_expands', 0)
    agent.set_data('hgm_output_dir', temp_output_dir)
    agent.set_data('hgm_alpha', 0.5)
    agent.set_data('hgm_total_tasks', ['task1', 'task2', 'task3'])

    # Mock _expand and _evaluate methods
    expand_called = False
    evaluate_called = False

    async def mock_expand(self):
        nonlocal expand_called
        expand_called = True
        from python.helpers.tool import Response
        return Response(message="Expanded successfully", break_loop=False)

    async def mock_evaluate(self):
        nonlocal evaluate_called
        evaluate_called = True
        from python.helpers.tool import Response
        return Response(message="Evaluated successfully", break_loop=False)

    # Patch the methods
    with patch.object(HGMSelfImprove, '_expand', new=mock_expand):
        with patch.object(HGMSelfImprove, '_evaluate', new=mock_evaluate):
            tool = HGMSelfImprove(
                agent=agent,
                name="hgm_self_improve_tool",
                method=None,
                args={
                    'operation': 'run',
                    'iterations': 1
                },
                message="",
                loop_data=None
            )

            response = await tool.execute()

    # Verify _evaluate was called, not _expand
    assert not expand_called
    assert evaluate_called
    assert 'evaluate: 1' in response.message.lower()


@pytest.mark.asyncio
async def test_run_multiple_iterations(agent_setup, temp_output_dir):
    """Test that _run() completes multiple iterations correctly"""
    from unittest.mock import patch
    from python.helpers.hgm_tree import TreeNode

    agent = agent_setup

    # Set up initial state
    root_node = TreeNode(commit_id="abc123", parent_id=None, node_id=0)
    agent.set_data('hgm_nodes', {0: root_node})
    agent.set_data('hgm_n_task_evals', 0)
    agent.set_data('hgm_n_pending_expands', 0)
    agent.set_data('hgm_output_dir', temp_output_dir)
    agent.set_data('hgm_alpha', 0.5)
    agent.set_data('hgm_total_tasks', ['task1', 'task2'])

    # Track calls
    calls = []

    async def mock_expand(self):
        calls.append('expand')
        # Simulate adding a node
        nodes = self.agent.get_data('hgm_nodes')
        new_id = max(nodes.keys()) + 1
        parent_commit = nodes[0].commit_id
        nodes[new_id] = TreeNode(commit_id=f"commit{new_id}", parent_id=parent_commit, node_id=new_id)
        self.agent.set_data('hgm_nodes', nodes)

        n_pending = self.agent.get_data('hgm_n_pending_expands') or 0
        self.agent.set_data('hgm_n_pending_expands', n_pending + 1)

        from python.helpers.tool import Response
        return Response(message="Expanded", break_loop=False)

    async def mock_evaluate(self):
        calls.append('evaluate')
        # Simulate evaluation
        n_evals = self.agent.get_data('hgm_n_task_evals') or 0
        self.agent.set_data('hgm_n_task_evals', n_evals + 1)

        from python.helpers.tool import Response
        return Response(message="Evaluated", break_loop=False)

    with patch.object(HGMSelfImprove, '_expand', new=mock_expand):
        with patch.object(HGMSelfImprove, '_evaluate', new=mock_evaluate):
            tool = HGMSelfImprove(
                agent=agent,
                name="hgm_self_improve_tool",
                method=None,
                args={
                    'operation': 'run',
                    'iterations': 5
                },
                message="",
                loop_data=None
            )

            response = await tool.execute()

    # Verify multiple calls were made
    assert len(calls) == 5
    assert 'iterations completed' in response.message.lower()


@pytest.mark.asyncio
async def test_run_tracks_statistics(agent_setup, temp_output_dir):
    """Test that _run() tracks and reports statistics correctly"""
    from unittest.mock import patch
    from python.helpers.hgm_tree import TreeNode

    agent = agent_setup

    # Set up initial state
    root_node = TreeNode(commit_id="abc123", parent_id=None, node_id=0)
    root_node.utility_measures = [1, 1, 0, 1]  # 75% success rate

    child_node = TreeNode(commit_id="def456", parent_id="abc123", node_id=1)
    child_node.utility_measures = [1, 1]  # 100% success rate

    agent.set_data('hgm_nodes', {0: root_node, 1: child_node})
    agent.set_data('hgm_n_task_evals', 6)
    agent.set_data('hgm_n_pending_expands', 0)
    agent.set_data('hgm_output_dir', temp_output_dir)
    agent.set_data('hgm_alpha', 0.5)
    agent.set_data('hgm_total_tasks', ['task1', 'task2', 'task3'])

    async def mock_expand(self):
        from python.helpers.tool import Response
        return Response(message="Expanded", break_loop=False)

    async def mock_evaluate(self):
        from python.helpers.tool import Response
        return Response(message="Evaluated", break_loop=False)

    with patch.object(HGMSelfImprove, '_expand', new=mock_expand):
        with patch.object(HGMSelfImprove, '_evaluate', new=mock_evaluate):
            tool = HGMSelfImprove(
                agent=agent,
                name="hgm_self_improve_tool",
                method=None,
                args={
                    'operation': 'run',
                    'iterations': 2
                },
                message="",
                loop_data=None
            )

            response = await tool.execute()

    # Verify statistics in response
    assert 'total nodes: 2' in response.message.lower()
    assert 'task evaluations: 6' in response.message.lower()
    # Best performing node should be child_node (utility=1.000)
    assert 'best performing node' in response.message.lower()
    assert 'utility=1.000' in response.message.lower()


@pytest.mark.asyncio
async def test_run_handles_no_nodes(agent_setup, temp_output_dir):
    """Test that _run() handles missing nodes gracefully"""
    agent = agent_setup

    # Don't set up any nodes
    agent.set_data('hgm_output_dir', temp_output_dir)

    tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve_tool",
        method=None,
        args={
            'operation': 'run',
            'iterations': 1
        },
        message="",
        loop_data=None
    )

    response = await tool.execute()

    # Should return error message
    assert 'not initialized' in response.message.lower() or 'error' in response.message.lower()


@pytest.mark.asyncio
async def test_calculate_tree_depth(agent_setup):
    """Test _calculate_tree_depth helper function"""
    from python.helpers.hgm_tree import TreeNode

    agent = agent_setup

    # Create tree: 0 -> 1 -> 2
    #                   \-> 3 -> 4 -> 5
    root = TreeNode(commit_id="commit0", parent_id=None, node_id=0)
    node1 = TreeNode(commit_id="commit1", parent_id="commit0", node_id=1)
    node2 = TreeNode(commit_id="commit2", parent_id="commit1", node_id=2)
    node3 = TreeNode(commit_id="commit3", parent_id="commit1", node_id=3)
    node4 = TreeNode(commit_id="commit4", parent_id="commit3", node_id=4)
    node5 = TreeNode(commit_id="commit5", parent_id="commit4", node_id=5)

    nodes = {0: root, 1: node1, 2: node2, 3: node3, 4: node4, 5: node5}

    # Set up the tree structure by adding children
    root.add_child(node1)
    node1.add_child(node2)
    node1.add_child(node3)
    node3.add_child(node4)
    node4.add_child(node5)

    agent.set_data('hgm_nodes', nodes)

    tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve_tool",
        method=None,
        args={'operation': 'run'},
        message="",
        loop_data=None
    )

    # Calculate depth starting from root
    depth = tool._calculate_tree_depth(root)

    # Depth should be 4 (longest path: 0 -> 1 -> 3 -> 4 -> 5)
    assert depth == 4
