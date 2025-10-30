# tests/unit/test_hgm_config_integration.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from agent import Agent, AgentContext, AgentConfig
from python.tools.hgm_self_improve_tool import HGMSelfImprove
from python.helpers.hgm_config import HGMConfig
from python.helpers.hgm_tree import TreeNode
import models


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


def test_get_config_returns_default(agent_setup):
    """Test that _get_config() returns default when no config set"""
    agent = agent_setup

    tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve",
        method=None,
        args={'operation': 'status'},
        message="",
        loop_data=None
    )

    config = tool._get_config()

    assert isinstance(config, HGMConfig)
    assert config.max_task_evals == 1000
    assert config.alpha == 0.5
    assert config.beta == 1.0


def test_get_config_from_dict(agent_setup):
    """Test that _get_config() converts dict to HGMConfig"""
    agent = agent_setup

    # Set dict config
    config_dict = {
        'max_task_evals': 500,
        'alpha': 0.7,
        'max_workers': 2
    }
    agent.set_data('hgm_config', config_dict)

    tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve",
        method=None,
        args={'operation': 'status'},
        message="",
        loop_data=None
    )

    config = tool._get_config()

    assert isinstance(config, HGMConfig)
    assert config.max_task_evals == 500
    assert config.alpha == 0.7
    assert config.max_workers == 2


def test_get_config_from_object(agent_setup):
    """Test that _get_config() returns existing HGMConfig object"""
    agent = agent_setup

    # Set HGMConfig object
    config_obj = HGMConfig(max_task_evals=250, alpha=0.3)
    agent.set_data('hgm_config_object', config_obj)

    tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve",
        method=None,
        args={'operation': 'status'},
        message="",
        loop_data=None
    )

    config = tool._get_config()

    assert config is config_obj
    assert config.max_task_evals == 250
    assert config.alpha == 0.3


def test_get_config_caches_object(agent_setup):
    """Test that _get_config() caches HGMConfig object"""
    agent = agent_setup

    # Set dict config only
    config_dict = {'max_task_evals': 500}
    agent.set_data('hgm_config', config_dict)

    tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve",
        method=None,
        args={'operation': 'status'},
        message="",
        loop_data=None
    )

    # First call should create and cache object
    config1 = tool._get_config()
    config2 = tool._get_config()

    # Should return same cached object
    assert config1 is config2


@pytest.mark.asyncio
async def test_initialize_with_dict_config(agent_setup):
    """Test initialize operation with dict config"""
    agent = agent_setup

    with patch('subprocess.run') as mock_subprocess:
        mock_result = MagicMock()
        mock_result.stdout = 'abc123\n'
        mock_subprocess.return_value = mock_result

        tool = HGMSelfImprove(
            agent=agent,
            name="hgm_self_improve",
            method=None,
            args={
                'operation': 'initialize',
                'output_dir': '/tmp/test_hgm',
                'config': {
                    'max_task_evals': 100,
                    'alpha': 0.3
                }
            },
            message="",
            loop_data=None
        )

        response = await tool.execute()

        # Check that config was stored correctly
        stored_config = agent.get_data('hgm_config')
        assert stored_config['max_task_evals'] == 100
        assert stored_config['alpha'] == 0.3

        # Check that HGMConfig object was stored
        config_obj = agent.get_data('hgm_config_object')
        assert isinstance(config_obj, HGMConfig)
        assert config_obj.max_task_evals == 100
        assert config_obj.alpha == 0.3


@pytest.mark.asyncio
async def test_initialize_with_hgmconfig_object(agent_setup):
    """Test initialize operation with HGMConfig object"""
    agent = agent_setup

    with patch('subprocess.run') as mock_subprocess:
        mock_result = MagicMock()
        mock_result.stdout = 'abc123\n'
        mock_subprocess.return_value = mock_result

        config = HGMConfig.create_fast()

        tool = HGMSelfImprove(
            agent=agent,
            name="hgm_self_improve",
            method=None,
            args={
                'operation': 'initialize',
                'output_dir': '/tmp/test_hgm',
                'config': config
            },
            message="",
            loop_data=None
        )

        response = await tool.execute()

        # Check that config was stored correctly
        stored_config_obj = agent.get_data('hgm_config_object')
        assert isinstance(stored_config_obj, HGMConfig)
        assert stored_config_obj.max_task_evals == 100
        assert stored_config_obj.alpha == 0.3


def test_config_validation_on_initialize(agent_setup):
    """Test that invalid config raises error during initialize"""
    agent = agent_setup

    tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve",
        method=None,
        args={
            'operation': 'initialize',
            'config': {
                'max_task_evals': -1  # Invalid
            }
        },
        message="",
        loop_data=None
    )

    # Should raise ValueError during config creation
    with pytest.raises(ValueError, match="max_task_evals must be positive"):
        import asyncio
        asyncio.run(tool.execute())


@pytest.mark.asyncio
async def test_expand_uses_config_parameters(agent_setup):
    """Test that expand operation uses config parameters"""
    agent = agent_setup

    # Setup state
    root_node = TreeNode(commit_id="abc123", parent_id=None, node_id=0)
    root_node.utility_measures = [0.5, 0.7]

    nodes = {0: root_node}
    agent.set_data('hgm_nodes', nodes)
    agent.set_data('hgm_output_dir', '/tmp/test_hgm')
    agent.set_data('hgm_n_task_evals', 0)
    agent.set_data('hgm_next_node_id', 1)

    config = HGMConfig(
        max_task_evals=100,
        alpha=0.3,
        beta=1.5,
        cool_down=10
    )
    agent.set_data('hgm_config_object', config)

    with patch('python.helpers.hgm_utils.HGMUtils') as mock_utils_class:
        mock_utils = MagicMock()
        mock_utils.sample_child = AsyncMock(return_value=("new_commit", 1))
        mock_utils_class.return_value = mock_utils

        tool = HGMSelfImprove(
            agent=agent,
            name="hgm_self_improve",
            method=None,
            args={
                'operation': 'expand',
                'git_dir': '/tmp',
                'total_tasks': []
            },
            message="",
            loop_data=None
        )

        response = await tool.execute()

        # Verify sample_child was called with config value
        mock_utils.sample_child.assert_called_once()
        call_args = mock_utils.sample_child.call_args
        assert call_args.kwargs['max_attempts'] == config.max_attempts_per_child


@pytest.mark.asyncio
async def test_run_uses_config_alpha(agent_setup):
    """Test that run operation uses config alpha value"""
    agent = agent_setup

    # Setup state
    root_node = TreeNode(commit_id="abc123", parent_id=None, node_id=0)
    nodes = {0: root_node}
    agent.set_data('hgm_nodes', nodes)
    agent.set_data('hgm_n_task_evals', 0)
    agent.set_data('hgm_output_dir', '/tmp/test_hgm')

    config = HGMConfig(alpha=0.8, max_task_evals=100)
    agent.set_data('hgm_config_object', config)

    with patch.object(HGMSelfImprove, '_expand', new_callable=AsyncMock) as mock_expand:
        mock_expand.return_value = MagicMock(message="expanded")

        tool = HGMSelfImprove(
            agent=agent,
            name="hgm_self_improve",
            method=None,
            args={
                'operation': 'run',
                'iterations': 1,
                'git_dir': '/tmp',
                'total_tasks': []
            },
            message="",
            loop_data=None
        )

        response = await tool.execute()

        # Should use config.alpha in decision rule
        # With n_task_evals=0, alpha=0.8, nodes=1: 0**0.8 = 0 >= 0, expand
        assert 'expand: 1' in response.message.lower()


def test_config_presets_integration(agent_setup):
    """Test that config presets work correctly"""
    agent = agent_setup

    # Test fast preset
    fast_config = HGMConfig.create_fast()
    tool = HGMSelfImprove(
        agent=agent,
        name="hgm_self_improve",
        method=None,
        args={
            'operation': 'initialize',
            'config': fast_config
        },
        message="",
        loop_data=None
    )

    config = tool._get_config()
    assert config.max_task_evals == 100
    assert config.max_workers == 1

    # Test thorough preset
    agent2 = agent_setup
    thorough_config = HGMConfig.create_thorough()
    tool2 = HGMSelfImprove(
        agent=agent2,
        name="hgm_self_improve",
        method=None,
        args={
            'operation': 'initialize',
            'config': thorough_config
        },
        message="",
        loop_data=None
    )

    config2 = tool2._get_config()
    assert config2.max_task_evals == 5000
    assert config2.max_workers == 8
