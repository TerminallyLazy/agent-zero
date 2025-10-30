# tests/unit/test_test_command_tool.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent import Agent, AgentContext, AgentConfig
from python.tools.test_command_tool import TestCommand
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


@pytest.mark.asyncio
async def test_test_command_swe_bench(agent_setup):
    """Test generating test command for SWE-bench repository"""
    agent = agent_setup

    # Mock LLM response
    mock_response = MagicMock()
    mock_response.content = """## Test Command

pytest tests/test_module.py::test_function -xvs

## Pre-requisites

- Ensure virtual environment is activated
- Install dependencies: pip install -r requirements.txt

## Expected Output

All tests should pass with no failures."""

    async def mock_llm_invoke(messages):
        return mock_response

    with patch.object(agent, 'get_utility_model') as mock_get_model:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = mock_llm_invoke
        mock_get_model.return_value = mock_llm

        tool = TestCommand(
            agent=agent,
            name="test_command",
            method=None,
            args={
                'repo_type': 'swe',
                'repo_context': 'Python repository using pytest',
                'test_info': 'Testing module functionality'
            },
            message="",
            loop_data=None
        )

        response = await tool.execute()

    # Verify response contains test command
    assert response.message is not None
    assert 'pytest' in response.message.lower()
    assert 'test_module.py' in response.message.lower()


@pytest.mark.asyncio
async def test_test_command_polyglot(agent_setup):
    """Test generating test command for polyglot repository"""
    agent = agent_setup

    # Mock LLM response
    mock_response = MagicMock()
    mock_response.content = """## Test Command

go test -v ./...

## Pre-requisites

- Go 1.19+ installed"""

    async def mock_llm_invoke(messages):
        return mock_response

    with patch.object(agent, 'get_utility_model') as mock_get_model:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = mock_llm_invoke
        mock_get_model.return_value = mock_llm

        tool = TestCommand(
            agent=agent,
            name="test_command",
            method=None,
            args={
                'repo_type': 'polyglot',
                'repo_context': 'Go repository',
                'test_info': 'Testing Go modules',
                'eval_script': 'go test -v ./...'
            },
            message="",
            loop_data=None
        )

        response = await tool.execute()

    # Verify response contains go test command
    assert response.message is not None
    assert 'go test' in response.message.lower()


@pytest.mark.asyncio
async def test_test_command_extraction(agent_setup):
    """Test test command extraction from markdown"""
    agent = agent_setup

    tool = TestCommand(
        agent=agent,
        name="test_command",
        method=None,
        args={},
        message="",
        loop_data=None
    )

    # Test extraction
    markdown = """## Test Command

pytest tests/test_file.py -xvs

## Pre-requisites

Some setup instructions"""

    command = tool._extract_test_command(markdown)
    assert command == "pytest tests/test_file.py -xvs"


@pytest.mark.asyncio
async def test_test_command_hgm_restrictions(agent_setup):
    """Test that HGM test commands include proper restrictions"""
    agent = agent_setup

    mock_response = MagicMock()
    mock_response.content = """## Test Command

pytest tests/unit/test_hgm_utils.py -xvs

## Notes

Do not test subordinate delegation or diagnostic tools directly"""

    async def mock_llm_invoke(messages):
        return mock_response

    with patch.object(agent, 'get_utility_model') as mock_get_model:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = mock_llm_invoke
        mock_get_model.return_value = mock_llm

        tool = TestCommand(
            agent=agent,
            name="test_command",
            method=None,
            args={
                'repo_type': 'hgm',
                'test_info': 'Testing HGM utilities'
            },
            message="",
            loop_data=None
        )

        response = await tool.execute()

    # Verify restrictions are mentioned
    assert 'subordinate' in response.message.lower() or 'diagnostic' in response.message.lower()
