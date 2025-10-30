# tests/integration/test_hgm_phase2_integration.py
"""
Integration tests for HGM Phase 2: Core Self-Improvement Loop

Tests the complete workflow from initialization through self-improvement iterations,
verifying that all components work together correctly.
"""
import pytest
import os
import tempfile
import json
from unittest.mock import AsyncMock, MagicMock, patch
from agent import Agent, AgentContext, AgentConfig
from python.tools.hgm_self_improve_tool import HGMSelfImprove
from python.helpers.hgm_tree import TreeNode
import models


@pytest.fixture
def temp_dirs():
    """Create temporary directories for git and output"""
    with tempfile.TemporaryDirectory() as git_dir:
        with tempfile.TemporaryDirectory() as output_dir:
            yield git_dir, output_dir


@pytest.fixture
def agent_setup():
    """Create agent with minimal configuration for testing"""
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
async def test_phase2_complete_workflow(agent_setup, temp_dirs):
    """
    Integration test for complete Phase 2 workflow:
    1. Initialize HGM system
    2. Run expand operation
    3. Run evaluate operation
    4. Run full orchestration loop
    """
    agent = agent_setup
    git_dir, output_dir = temp_dirs

    # ============================================================
    # STEP 1: Initialize HGM System
    # ============================================================

    init_tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve_tool",
        method=None,
        args={
            'operation': 'initialize',
            'git_dir': git_dir,
            'output_dir': output_dir,
            'total_tasks': ['task1', 'task2', 'task3'],
            'agent_profile': 'test_agent',
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

    with patch('subprocess.run') as mock_subprocess:
        # Mock git rev-parse to return root commit
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="root_commit_123",
            stderr=""
        )

        response = await init_tool.execute()

    # Verify initialization
    assert 'initialized' in response.message.lower()
    nodes = agent.get_data('hgm_nodes')
    assert nodes is not None
    assert 0 in nodes
    assert nodes[0].commit_id == "root_commit_123"

    # ============================================================
    # STEP 2: Test Expand Operation
    # ============================================================

    # Set up for expand test
    from python.tools.diagnostic_tool import Diagnostic
    from python.tools.call_subordinate import Delegation

    # Mock diagnostic analysis
    mock_diagnosis = {
        "log_summarization": "Agent failed to implement changes",
        "potential_improvements": [
            "Add validation before completing",
            "Improve error handling"
        ],
        "improvement_proposal": "Add validation to ensure changes are made",
        "implementation_suggestion": "Modify sample_child() to verify git diff",
        "problem_description": "## Fix Empty Patch Generation\n\nAdd validation..."
    }

    async def mock_diagnostic_execute(self):
        from python.helpers.tool import Response
        return Response(
            message=json.dumps(mock_diagnosis, indent=2),
            break_loop=False
        )

    async def mock_delegation_execute(self):
        from python.helpers.tool import Response
        return Response(
            message="Changes implemented successfully",
            break_loop=False
        )

    def mock_git_run(*args, **kwargs):
        cmd = args[0] if args else []
        if 'rev-parse' in cmd:
            # Return different commit for child
            return MagicMock(
                returncode=0,
                stdout="child_commit_abc",
                stderr=""
            )
        elif 'reset' in cmd:
            return MagicMock(returncode=0, stdout="", stderr="")
        elif 'diff' in cmd:
            return MagicMock(returncode=0, stdout="", stderr="")
        else:
            return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(Diagnostic, 'execute', new=mock_diagnostic_execute):
        with patch.object(Delegation, 'execute', new=mock_delegation_execute):
            with patch('subprocess.run', side_effect=mock_git_run):
                expand_tool = HGMSelfImprove(
                    agent=agent,
                    name="hgm_self_improve_tool",
                    method=None,
                    args={'operation': 'expand'},
                    message="",
                    loop_data=None
                )

                response = await expand_tool.execute()

    # Verify expand created a new node
    assert 'expand' in response.message.lower()
    nodes = agent.get_data('hgm_nodes')
    assert len(nodes) == 2  # Root + child
    assert 1 in nodes
    assert nodes[1].parent_id == "root_commit_123"

    # ============================================================
    # STEP 3: Test Evaluate Operation
    # ============================================================

    # Mock repository solver for evaluation
    from python.tools.repo_solver_tool import RepoSolver

    async def mock_solver_execute(self):
        from python.helpers.tool import Response
        # Simulate successful task completion
        return Response(
            message="Task completed successfully",
            break_loop=False
        )

    def mock_git_for_eval(*args, **kwargs):
        cmd = args[0] if args else []
        if 'reset' in cmd:
            return MagicMock(returncode=0, stdout="", stderr="")
        elif 'diff' in cmd:
            # Return non-empty diff to indicate changes
            return MagicMock(
                returncode=0,
                stdout="diff --git a/file.py\n+new line",
                stderr=""
            )
        else:
            return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(RepoSolver, 'execute', new=mock_solver_execute):
        with patch('subprocess.run', side_effect=mock_git_for_eval):
            evaluate_tool = HGMSelfImprove(
                agent=agent,
                name="hgm_self_improve_tool",
                method=None,
                args={'operation': 'evaluate'},
                message="",
                loop_data=None
            )

            response = await evaluate_tool.execute()

    # Verify evaluation updated utility measures
    assert 'evaluate' in response.message.lower()
    nodes = agent.get_data('hgm_nodes')
    # At least one node should have been evaluated
    total_evals = sum(len(node.utility_measures) for node in nodes.values())
    assert total_evals > 0

    # ============================================================
    # STEP 4: Test Full Orchestration Loop
    # ============================================================

    # Set up state for orchestration
    agent.set_data('hgm_n_task_evals', 0)
    agent.set_data('hgm_n_pending_expands', 0)

    # Mock both expand and evaluate operations
    expand_count = 0
    evaluate_count = 0

    async def mock_expand(self):
        nonlocal expand_count
        expand_count += 1
        # Simulate adding a node
        nodes = self.agent.get_data('hgm_nodes')
        new_id = max(nodes.keys()) + 1
        parent_commit = nodes[0].commit_id
        nodes[new_id] = TreeNode(
            commit_id=f"commit{new_id}",
            parent_id=parent_commit,
            node_id=new_id
        )
        self.agent.set_data('hgm_nodes', nodes)

        n_pending = self.agent.get_data('hgm_n_pending_expands') or 0
        self.agent.set_data('hgm_n_pending_expands', n_pending + 1)

        from python.helpers.tool import Response
        return Response(message="Expanded", break_loop=False)

    async def mock_evaluate(self):
        nonlocal evaluate_count
        evaluate_count += 1
        # Simulate evaluation
        n_evals = self.agent.get_data('hgm_n_task_evals') or 0
        self.agent.set_data('hgm_n_task_evals', n_evals + 1)

        # Add a utility measure to a random node
        nodes = self.agent.get_data('hgm_nodes')
        if nodes:
            node = list(nodes.values())[0]
            node.utility_measures.append(1)

        from python.helpers.tool import Response
        return Response(message="Evaluated", break_loop=False)

    with patch.object(HGMSelfImprove, '_expand', new=mock_expand):
        with patch.object(HGMSelfImprove, '_evaluate', new=mock_evaluate):
            run_tool = HGMSelfImprove(
                agent=agent,
                name="hgm_self_improve_tool",
                method=None,
                args={
                    'operation': 'run',
                    'iterations': 10
                },
                message="",
                loop_data=None
            )

            response = await run_tool.execute()

    # Verify orchestration completed
    assert '10/10' in response.message or 'iterations completed: 10' in response.message.lower()
    assert expand_count > 0
    assert evaluate_count > 0
    assert expand_count + evaluate_count == 10

    # Verify statistics are reported
    assert 'total nodes' in response.message.lower()
    assert 'task evaluations' in response.message.lower()
    assert 'best performing node' in response.message.lower()

    # ============================================================
    # VERIFICATION: End-to-End State
    # ============================================================

    # Verify final state
    nodes = agent.get_data('hgm_nodes')
    assert len(nodes) >= 2  # At least root + children

    n_task_evals = agent.get_data('hgm_n_task_evals')
    assert n_task_evals > 0

    # Verify tree structure is maintained
    for node_id, node in nodes.items():
        assert node.node_id == node_id
        if node.parent_id is not None:
            # Parent should exist in nodes (by commit_id)
            parent_exists = any(
                n.commit_id == node.parent_id
                for n in nodes.values()
            )
            assert parent_exists, f"Parent {node.parent_id} not found for node {node_id}"


@pytest.mark.asyncio
async def test_phase2_error_handling(agent_setup, temp_dirs):
    """Test that Phase 2 handles errors gracefully"""
    agent = agent_setup
    git_dir, output_dir = temp_dirs

    # Test expand with diagnostic failure
    from python.tools.diagnostic_tool import Diagnostic

    async def mock_diagnostic_failure(self):
        from python.helpers.tool import Response
        return Response(
            message="Error: Diagnostic analysis failed",
            break_loop=False
        )

    # Initialize first
    agent.set_data('hgm_nodes', {
        0: TreeNode(commit_id="root", parent_id=None, node_id=0)
    })
    agent.set_data('hgm_git_dir', git_dir)
    agent.set_data('hgm_output_dir', output_dir)
    agent.set_data('hgm_total_tasks', ['task1'])
    agent.set_data('hgm_alpha', 0.5)

    with patch.object(Diagnostic, 'execute', new=mock_diagnostic_failure):
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )

            expand_tool = HGMSelfImprove(
                agent=agent,
                name="hgm_self_improve_tool",
                method=None,
                args={'operation': 'expand'},
                message="",
                loop_data=None
            )

            response = await expand_tool.execute()

    # Should handle error gracefully
    assert response.message is not None
    # Original node should still exist
    nodes = agent.get_data('hgm_nodes')
    assert 0 in nodes


@pytest.mark.asyncio
async def test_phase2_decision_logic(agent_setup):
    """Test that the decision rule in _run() works correctly"""
    agent = agent_setup

    # Test various scenarios
    test_cases = [
        # (n_task_evals, alpha, num_nodes, n_pending_expands, expected_expand)
        (4, 0.5, 2, 0, True),   # 4**0.5=2.0 >= 2-1+0=1 -> expand
        (1, 0.5, 5, 0, False),  # 1**0.5=1.0 < 5-1+0=4 -> evaluate
        (9, 0.5, 4, 0, True),   # 9**0.5=3.0 >= 4-1+0=3 -> expand
        (16, 0.5, 10, 2, False), # 16**0.5=4.0 < 10-1+2=11 -> evaluate
    ]

    for n_evals, alpha, n_nodes, n_pending, expected_expand in test_cases:
        # Set up state
        nodes = {
            i: TreeNode(
                commit_id=f"commit{i}",
                parent_id=f"commit{i-1}" if i > 0 else None,
                node_id=i
            )
            for i in range(n_nodes)
        }

        agent.set_data('hgm_nodes', nodes)
        agent.set_data('hgm_n_task_evals', n_evals)
        agent.set_data('hgm_n_pending_expands', n_pending)
        agent.set_data('hgm_output_dir', '/tmp')
        agent.set_data('hgm_alpha', alpha)
        agent.set_data('hgm_total_tasks', ['task1', 'task2'])

        # Track which operation was called
        expand_called = False
        evaluate_called = False

        async def mock_expand(self):
            nonlocal expand_called
            expand_called = True
            from python.helpers.tool import Response
            return Response(message="Expanded", break_loop=False)

        async def mock_evaluate(self):
            nonlocal evaluate_called
            evaluate_called = True
            from python.helpers.tool import Response
            return Response(message="Evaluated", break_loop=False)

        with patch.object(HGMSelfImprove, '_expand', new=mock_expand):
            with patch.object(HGMSelfImprove, '_evaluate', new=mock_evaluate):
                tool = HGMSelfImprove(
                    agent=agent,
                    name="hgm_self_improve_tool",
                    method=None,
                    args={'operation': 'run', 'iterations': 1},
                    message="",
                    loop_data=None
                )

                await tool.execute()

        # Verify decision
        if expected_expand:
            assert expand_called and not evaluate_called, \
                f"Expected expand for n_evals={n_evals}, alpha={alpha}, n_nodes={n_nodes}, n_pending={n_pending}"
        else:
            assert evaluate_called and not expand_called, \
                f"Expected evaluate for n_evals={n_evals}, alpha={alpha}, n_nodes={n_nodes}, n_pending={n_pending}"
