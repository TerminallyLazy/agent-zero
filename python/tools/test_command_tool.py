# python/tools/test_command_tool.py
from python.helpers.tool import Tool, Response
import os


class TestCommand(Tool):
    """
    Tool for generating test execution instructions for coding tasks.

    Generates appropriate test commands based on repository type:
    - SWE-bench: pytest with specific file notation
    - Polyglot: Language-specific test frameworks
    - HGM: pytest with restrictions on certain modules
    """

    async def execute(self, **kwargs) -> Response:
        repo_type = self.args.get('repo_type', 'swe')
        repo_context = self.args.get('repo_context', '')
        test_info = self.args.get('test_info', '')
        eval_script = self.args.get('eval_script', '')

        # Build prompt using template
        prompt = self.agent.read_prompt(
            "hgm.test_command.md",
            repo_context=repo_context,
            test_info=test_info,
            eval_script=eval_script
        )

        # Get LLM response
        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=prompt)]

        llm = self.agent.get_utility_model()
        response = await llm.ainvoke(messages)

        # Parse the response to extract test command
        content = response.content

        # Extract test command from markdown
        test_command = self._extract_test_command(content)

        return Response(
            message=f"""Test Command Generated:

{content}

Extracted Command: {test_command}""",
            break_loop=False
        )

    def _extract_test_command(self, content: str) -> str:
        """Extract the test command from markdown response"""
        lines = content.split('\n')
        in_command_section = False
        command = ""

        for line in lines:
            if '## Test Command' in line:
                in_command_section = True
                continue
            elif in_command_section:
                if line.startswith('##'):
                    break
                if line.strip() and not line.startswith('```'):
                    command = line.strip()
                    break

        return command if command else "pytest <file> -xvs"

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://terminal Test Command: {self.args.get('repo_type', 'unknown')}",
            content="",
            kvps=self.args,
        )
