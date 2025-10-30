# python/tools/diagnostic_tool.py
from python.helpers.tool import Tool, Response
import json
import os

class Diagnostic(Tool):
    """
    Tool for analyzing failed attempts and generating improvement recommendations.

    Analysis strategies:
    - swe: Analyze SWE-bench failures (general)
    - empty_patch: Diagnose empty patch generation
    - stochasticity: Analyze consistency/stochastic behavior issues
    - contextlength: Analyze context length issues
    - polyglot: Analyze multi-language issues
    - problem_description: Convert diagnosis to GitHub issue format
    """

    async def execute(self, **kwargs) -> Response:
        strategy = self.args.get('strategy', 'swe')
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

        # Route to appropriate analysis method
        if strategy == 'swe':
            return await self._analyze_swe(log_content, problem_statement)
        elif strategy == 'empty_patch':
            return await self._analyze_empty_patch(log_content, problem_statement)
        elif strategy == 'stochasticity':
            return await self._analyze_stochasticity(log_content, problem_statement)
        elif strategy == 'contextlength':
            return await self._analyze_contextlength(log_content, problem_statement)
        elif strategy == 'polyglot':
            return await self._analyze_polyglot(log_content, problem_statement)
        elif strategy == 'problem_description':
            return await self._generate_problem_description()
        else:
            return Response(
                message=f"Error: Unknown strategy '{strategy}'",
                break_loop=False
            )

    async def _analyze_swe(self, log_content: str, problem_statement: str) -> Response:
        """Analyze SWE-bench failure using comprehensive diagnostic prompt"""
        generated_patch = self.args.get('generated_patch', '')
        test_results = self.args.get('test_results', '')
        test_patch = self.args.get('test_patch', '')

        # Build analysis prompt using enhanced template
        prompt = self.agent.read_prompt(
            "hgm.diagnose.swe.md",
            log=log_content,
            issue=problem_statement,
            patch=generated_patch,
            test_patch=test_patch,
            results=test_results
        )

        # Get diagnostic analysis
        result = await self._get_diagnostic_response(prompt)

        return Response(
            message=json.dumps(result, indent=2),
            break_loop=False
        )

    async def _analyze_empty_patch(self, log_content: str, problem_statement: str) -> Response:
        """Diagnose empty patch generation"""
        generated_patch = self.args.get('generated_patch', '')
        test_results = self.args.get('test_results', '')

        prompt = self.agent.read_prompt(
            "hgm.diagnostic.empty_patch.md",
            log=log_content,
            issue=problem_statement,
            patch=generated_patch,
            results=test_results
        )

        result = await self._get_diagnostic_response(prompt)

        return Response(
            message=json.dumps(result, indent=2),
            break_loop=False
        )

    async def _analyze_stochasticity(self, log_content: str, problem_statement: str) -> Response:
        """Analyze stochastic behavior / consistency issues"""
        test_results = self.args.get('test_results', '')

        prompt = self.agent.read_prompt(
            "hgm.diagnostic.stochasticity.md",
            log=log_content,
            issue=problem_statement,
            results=test_results
        )

        result = await self._get_diagnostic_response(prompt)

        return Response(
            message=json.dumps(result, indent=2),
            break_loop=False
        )

    async def _analyze_contextlength(self, log_content: str, problem_statement: str) -> Response:
        """Analyze context length issues"""
        # Use SWE prompt but focus on context-related aspects
        generated_patch = self.args.get('generated_patch', '')
        test_results = self.args.get('test_results', '')

        prompt = self.agent.read_prompt(
            "hgm.diagnose.swe.md",
            log=log_content,
            issue=problem_statement,
            patch=generated_patch,
            test_patch='',
            results=test_results
        )

        # Add context-specific guidance
        prompt += "\n\nIMPORTANT: Focus your analysis on context window limitations and how they affected the agent's performance."

        result = await self._get_diagnostic_response(prompt)

        return Response(
            message=json.dumps(result, indent=2),
            break_loop=False
        )

    async def _analyze_polyglot(self, log_content: str, problem_statement: str) -> Response:
        """Analyze multi-language / polyglot issues"""
        generated_patch = self.args.get('generated_patch', '')
        test_results = self.args.get('test_results', '')

        prompt = self.agent.read_prompt(
            "hgm.diagnose.polyglot.md",
            log=log_content,
            issue=problem_statement,
            patch=generated_patch,
            results=test_results
        )

        result = await self._get_diagnostic_response(prompt)

        return Response(
            message=json.dumps(result, indent=2),
            break_loop=False
        )

    async def _generate_problem_description(self) -> Response:
        """Convert diagnosis to GitHub issue format"""
        diagnosis = self.args.get('diagnosis', '')
        agent_summary = self.args.get('agent_summary', 'Agent Zero HGM Self-Improving Coding Agent')

        if not diagnosis:
            return Response(
                message="Error: No diagnosis provided. Run a diagnostic analysis first.",
                break_loop=False
            )

        prompt = self.agent.read_prompt(
            "hgm.problem_description.md",
            agent_summary=agent_summary,
            diagnosis=diagnosis
        )

        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=prompt)]

        llm = self.agent.get_utility_model()
        response = await llm.ainvoke(messages)

        # Return the GitHub issue markdown directly
        return Response(
            message=response.content,
            break_loop=False
        )

    async def _get_diagnostic_response(self, prompt: str) -> dict:
        """
        Send diagnostic prompt to LLM and parse JSON response.

        Returns dict with required fields:
        - log_summarization
        - potential_improvements
        - improvement_proposal
        - implementation_suggestion
        - problem_description
        """
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

            # Parse JSON
            result = json.loads(content)

            # Validate required fields
            required_fields = [
                'log_summarization',
                'potential_improvements',
                'improvement_proposal',
                'implementation_suggestion',
                'problem_description'
            ]

            for field in required_fields:
                if field not in result:
                    result[field] = f"[Error: {field} not provided]"

            # Ensure potential_improvements is a list
            if not isinstance(result['potential_improvements'], list):
                result['potential_improvements'] = [str(result['potential_improvements'])]

            return result

        except (json.JSONDecodeError, ValueError) as e:
            # Return error structure if JSON parsing fails
            error_result = {
                "error": "Failed to parse diagnostic response as JSON",
                "raw_response": content,
                "exception": str(e),
                "log_summarization": "[Parse error]",
                "potential_improvements": [],
                "improvement_proposal": "[Parse error]",
                "implementation_suggestion": "[Parse error]",
                "problem_description": "[Parse error]"
            }
            return error_result

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://psychology Diagnostic: {self.args.get('analysis_type', 'unknown')}",
            content="",
            kvps=self.args,
        )
