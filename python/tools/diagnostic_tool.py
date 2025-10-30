# python/tools/diagnostic_tool.py
from python.helpers.tool import Tool, Response
import json
import os

class Diagnostic(Tool):
    """
    Tool for analyzing failed attempts and generating improvement recommendations.

    Analysis types:
    - failure_analysis: Analyze failed solution attempts
    - empty_patch: Diagnose empty patch generation
    - stochasticity: Analyze stochastic behavior issues
    """

    async def execute(self, **kwargs) -> Response:
        analysis_type = self.args.get('analysis_type', 'failure_analysis')
        log_file = self.args.get('log_file', '')
        problem_statement = self.args.get('problem_statement', '')

        # Validate log file
        if log_file and not os.path.exists(log_file):
            return Response(
                message=f"Error: Log file not found: {log_file}",
                break_loop=False
            )

        # Read log if provided
        log_content = ""
        if log_file:
            with open(log_file, 'r') as f:
                log_content = f.read()

        if analysis_type == 'failure_analysis':
            return await self._analyze_failure(log_content, problem_statement)
        elif analysis_type == 'empty_patch':
            return await self._analyze_empty_patch(log_content, problem_statement)
        elif analysis_type == 'stochasticity':
            return await self._analyze_stochasticity(log_content, problem_statement)
        else:
            return Response(
                message=f"Error: Unknown analysis_type '{analysis_type}'",
                break_loop=False
            )

    async def _analyze_failure(self, log_content: str, problem_statement: str) -> Response:
        """Analyze failed solution attempt"""
        generated_patch = self.args.get('generated_patch', '')
        test_results = self.args.get('test_results', '')
        test_patch = self.args.get('test_patch', '')

        # Build analysis prompt
        prompt = self.agent.read_prompt(
            "hgm.diagnostic.failure_analysis.md",
            log=log_content,
            issue=problem_statement,
            patch=generated_patch,
            test_patch=test_patch,
            results=test_results
        )

        # Use utility model for analysis
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content=prompt)]

        # Get LLM response
        llm = self.agent.get_utility_model()
        response = await llm.ainvoke(messages)

        # Parse and validate JSON response
        try:
            # Extract JSON from response (might be wrapped in markdown)
            content = response.content
            if '```json' in content:
                json_start = content.index('```json') + 7
                json_end = content.rindex('```')
                content = content[json_start:json_end].strip()
            elif '```' in content:
                json_start = content.index('```') + 3
                json_end = content.rindex('```')
                content = content[json_start:json_end].strip()

            # Validate JSON structure
            result = json.loads(content)
            required_fields = [
                'log_summarization',
                'potential_improvements',
                'improvement_proposal',
                'implementation_suggestion'
            ]

            for field in required_fields:
                if field not in result:
                    result[field] = f"[Error: {field} not provided]"

            # Ensure potential_improvements is a list
            if not isinstance(result['potential_improvements'], list):
                result['potential_improvements'] = [str(result['potential_improvements'])]

            return Response(
                message=json.dumps(result, indent=2),
                break_loop=False
            )

        except (json.JSONDecodeError, ValueError) as e:
            # Return raw response if JSON parsing fails
            error_result = {
                "error": "Failed to parse diagnostic response as JSON",
                "raw_response": content,
                "exception": str(e)
            }
            return Response(
                message=json.dumps(error_result, indent=2),
                break_loop=False
            )

    async def _analyze_empty_patch(self, log_content: str, problem_statement: str) -> Response:
        """Diagnose empty patch generation"""
        prompt = self.agent.read_prompt(
            "hgm.diagnostic.empty_patch.md",
            log=log_content,
            issue=problem_statement
        )

        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=prompt)]

        llm = self.agent.get_utility_model()
        response = await llm.ainvoke(messages)

        # Return structured advice
        result = {
            "diagnosis": "Empty patch generated",
            "log_summarization": log_content[:500] + "..." if len(log_content) > 500 else log_content,
            "potential_causes": [
                "Agent didn't understand the problem",
                "Agent thought changes were not needed",
                "Agent made changes outside the repository",
                "Tool execution failed silently"
            ],
            "recommendations": response.content
        }

        return Response(
            message=json.dumps(result, indent=2),
            break_loop=False
        )

    async def _analyze_stochasticity(self, log_content: str, problem_statement: str) -> Response:
        """Analyze stochastic behavior"""
        prompt = self.agent.read_prompt(
            "hgm.diagnostic.stochasticity.md",
            log=log_content,
            issue=problem_statement
        )

        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=prompt)]

        llm = self.agent.get_utility_model()
        response = await llm.ainvoke(messages)

        result = {
            "analysis_type": "stochasticity",
            "observations": response.content
        }

        return Response(
            message=json.dumps(result, indent=2),
            break_loop=False
        )

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://psychology Diagnostic: {self.args.get('analysis_type', 'unknown')}",
            content="",
            kvps=self.args,
        )
