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
