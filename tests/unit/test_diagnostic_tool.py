# tests/unit/test_diagnostic_tool.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from agent import Agent, AgentContext, AgentConfig
from python.tools.diagnostic_tool import Diagnostic
import models

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
async def test_failure_analysis(agent_setup, tmp_path):
    """Verify failure analysis generates recommendations"""
    agent = agent_setup

    # Create sample log file
    log_file = tmp_path / "execution.log"
    log_file.write_text("""
[Agent] Starting to solve problem
[Agent] Analyzing file structure
[Agent] Attempting to modify authentication.py
[Error] NameError: name 'user_db' is not defined
[Agent] Failed to complete solution
""")

    problem_statement = "Fix login authentication bug"
    generated_patch = """
diff --git a/auth.py b/auth.py
--- a/auth.py
+++ b/auth.py
@@ -10,7 +10,7 @@
 def login(username, password):
-    return False
+    if user_db.check(username, password):
+        return True
"""

    test_results = "FAILED: test_login - NameError"

    # Mock the LLM response
    mock_llm_response = MagicMock()
    mock_llm_response.content = '''```json
{
  "log_summarization": "Agent attempted to implement login by checking user_db but referenced undefined variable",
  "potential_improvements": [
    "Add import statement for user_db module",
    "Initialize user_db before use",
    "Add better error handling for missing dependencies"
  ],
  "improvement_proposal": "Add import statement for user_db module",
  "implementation_suggestion": "Add 'from database import user_db' at the top of the file",
  "problem_description": "Missing import statement for user_db dependency"
}
```'''

    with patch.object(agent, 'get_utility_model') as mock_get_model:
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_llm_response)
        mock_get_model.return_value = mock_model

        tool = Diagnostic(
            agent=agent,
            name="diagnostic_tool",
            method=None,
            args={
                'analysis_type': 'failure_analysis',
                'log_file': str(log_file),
                'problem_statement': problem_statement,
                'generated_patch': generated_patch,
                'test_results': test_results
            },
            message="",
            loop_data=None
        )

        response = await tool.execute()

    # Should return JSON with required fields
    assert response.message is not None
    try:
        result = json.loads(response.message)
        assert 'log_summarization' in result
        assert 'potential_improvements' in result
        assert 'improvement_proposal' in result
        assert 'implementation_suggestion' in result
        assert isinstance(result['potential_improvements'], list)
    except json.JSONDecodeError:
        pytest.fail("Response should be valid JSON")
