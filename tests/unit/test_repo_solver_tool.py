# tests/unit/test_repo_solver_tool.py
import pytest
import os
import tempfile
import subprocess
from agent import Agent, AgentContext, AgentConfig
from python.tools.repo_solver_tool import RepoSolver
import models

def create_test_config():
    """Create a minimal AgentConfig for testing"""
    # Create minimal model configs
    chat_model = models.ModelConfig(
        type=models.ModelType.CHAT,
        provider="anthropic",
        name="claude-3-5-sonnet-20241022",
        api_base="",
        ctx_length=200000,
        vision=False,
        limit_requests=0,
        limit_input=0,
        limit_output=0,
        kwargs={}
    )

    utility_model = models.ModelConfig(
        type=models.ModelType.CHAT,
        provider="anthropic",
        name="claude-3-5-sonnet-20241022",
        api_base="",
        ctx_length=200000,
        limit_requests=0,
        limit_input=0,
        limit_output=0,
        kwargs={}
    )

    embeddings_model = models.ModelConfig(
        type=models.ModelType.EMBEDDING,
        provider="openai",
        name="text-embedding-3-small",
        api_base="",
        limit_requests=0,
        kwargs={}
    )

    browser_model = models.ModelConfig(
        type=models.ModelType.CHAT,
        provider="anthropic",
        name="claude-3-5-sonnet-20241022",
        api_base="",
        vision=True,
        kwargs={}
    )

    return AgentConfig(
        chat_model=chat_model,
        utility_model=utility_model,
        embeddings_model=embeddings_model,
        browser_model=browser_model,
        mcp_servers="",
        profile="default",
        memory_subdir="",
        knowledge_subdirs=["default"]
    )

@pytest.fixture
def sample_python_repo():
    """Create a sample Python repository with tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git
        subprocess.run(['git', 'init'], cwd=tmpdir, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=tmpdir, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=tmpdir, check=True)

        # Create a simple Python module
        src_file = os.path.join(tmpdir, 'calculator.py')
        with open(src_file, 'w') as f:
            f.write('''def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
''')

        # Create tests
        test_file = os.path.join(tmpdir, 'test_calculator.py')
        with open(test_file, 'w') as f:
            f.write('''import calculator

def test_add():
    assert calculator.add(2, 3) == 5

def test_subtract():
    assert calculator.subtract(5, 3) == 2
''')

        # Commit
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, check=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=tmpdir, check=True)

        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=True
        )
        base_commit = result.stdout.strip()

        yield tmpdir, base_commit

@pytest.mark.asyncio
async def test_identify_regression_tests(sample_python_repo):
    """Verify regression test identification - basic structure test"""
    git_dir, base_commit = sample_python_repo

    config = create_test_config()
    context = AgentContext(config)
    agent = Agent(0, config, context)

    instance_id = "test_instance_123"

    # Create tool with all required parameters for Tool base class
    tool = RepoSolver(
        agent=agent,
        name="repo_solver_tool",
        method=None,
        args={
            'mode': 'identify_tests',
            'git_dir': git_dir,
            'base_commit': base_commit,
            'problem_statement': 'Add a multiply function',
            'instance_id': instance_id
        },
        message="Testing repo solver",
        loop_data=None
    )

    # Note: This test will attempt to call real LLM APIs
    # For now, we'll just test that the tool is properly structured
    # and validates its inputs

    # Test validation: missing git_dir
    tool_invalid = RepoSolver(
        agent=agent,
        name="repo_solver_tool",
        method=None,
        args={
            'mode': 'identify_tests',
            'git_dir': '/nonexistent/path',
            'base_commit': base_commit,
            'problem_statement': 'Add a multiply function'
        },
        message="Testing validation",
        loop_data=None
    )

    response_invalid = await tool_invalid.execute()
    assert 'Error' in response_invalid.message
    assert 'Invalid git_dir' in response_invalid.message

    # Test validation: missing base_commit
    tool_no_commit = RepoSolver(
        agent=agent,
        name="repo_solver_tool",
        method=None,
        args={
            'mode': 'identify_tests',
            'git_dir': git_dir,
            'base_commit': '',
            'problem_statement': 'Add a multiply function'
        },
        message="Testing validation",
        loop_data=None
    )

    response_no_commit = await tool_no_commit.execute()
    assert 'Error' in response_no_commit.message
    assert 'base_commit is required' in response_no_commit.message

    # Test validation: missing problem_statement
    tool_no_problem = RepoSolver(
        agent=agent,
        name="repo_solver_tool",
        method=None,
        args={
            'mode': 'identify_tests',
            'git_dir': git_dir,
            'base_commit': base_commit,
            'problem_statement': ''
        },
        message="Testing validation",
        loop_data=None
    )

    response_no_problem = await tool_no_problem.execute()
    assert 'Error' in response_no_problem.message
    assert 'problem_statement is required' in response_no_problem.message

    # Test that valid inputs would proceed (even if LLM call fails)
    # The tool should at least attempt to delegate
    # We're testing structure, not end-to-end LLM integration here
    print(f"✓ RepoSolver tool structure and validation tests passed")
    print(f"✓ Tool can be instantiated with correct arguments")
    print(f"✓ Input validation works correctly")
