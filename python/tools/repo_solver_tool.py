# python/tools/repo_solver_tool.py
from python.helpers.tool import Tool, Response
from python.tools.call_subordinate import Delegation
import os
import time

class RepoSolver(Tool):
    """
    Tool for solving repository problems using subordinate agents.

    Modes:
    - identify_tests: Find regression tests for a problem
    - solve: Generate solution patch for a problem
    - run_tests: Execute identified regression tests
    """

    async def execute(self, **kwargs) -> Response:
        await self.agent.handle_intervention()

        mode = self.args.get('mode', 'solve')
        git_dir = self.args.get('git_dir', '')
        base_commit = self.args.get('base_commit', '')
        problem_statement = self.args.get('problem_statement', '')

        # Validate required args
        if not git_dir or not os.path.exists(git_dir):
            return Response(
                message=f"Error: Invalid git_dir: {git_dir}",
                break_loop=False
            )

        if not base_commit:
            return Response(
                message="Error: base_commit is required",
                break_loop=False
            )

        if not problem_statement:
            return Response(
                message="Error: problem_statement is required",
                break_loop=False
            )

        instance_id = self.args.get('instance_id', f"repo_{int(time.time())}")

        if mode == 'identify_tests':
            return await self._identify_tests(git_dir, base_commit, problem_statement, instance_id)
        elif mode == 'solve':
            return await self._solve_problem(git_dir, base_commit, problem_statement, instance_id)
        elif mode == 'run_tests':
            return await self._run_tests(git_dir, instance_id)
        else:
            return Response(
                message=f"Error: Unknown mode '{mode}'",
                break_loop=False
            )

    async def _identify_tests(self, git_dir: str, base_commit: str, problem_statement: str, instance_id: str) -> Response:
        """Identify regression tests for the problem"""

        # Use call_subordinate to analyze repository
        delegation = Delegation(
            agent=self.agent,
            name="call_subordinate",
            method=None,
            args={
                'message': f"""Analyze this repository to identify regression tests:

Repository: {git_dir}
Base commit: {base_commit}

Problem to solve: {problem_statement}

Your task:
1. Explore the repository structure
2. Find test files (typically in test/, tests/, or files starting with test_)
3. Identify which tests are relevant for regression testing
4. Return a summary of:
   - Test file paths
   - Test function/method names
   - How to run these tests (e.g., pytest command)

Be concise and specific.""",
                'reset': 'true'
            },
            message="Delegating test identification to subordinate",
            loop_data=None
        )

        # Execute delegation
        response = await delegation.execute()

        # Store test information in agent data
        self.agent.set_data(f"repo_solver_{instance_id}_tests", response.message)

        return response

    async def _solve_problem(self, git_dir: str, base_commit: str, problem_statement: str, instance_id: str) -> Response:
        """Generate solution for the problem"""

        timeout = self.args.get('timeout', 3600)
        test_description = self.args.get('test_description', '')

        # Build comprehensive prompt
        solve_prompt = f"""You are a coding agent tasked with solving a repository problem.

Repository: {git_dir}
Base commit: {base_commit}

Problem Statement:
{problem_statement}

"""

        if test_description:
            solve_prompt += f"""Test Requirements:
{test_description}

"""

        solve_prompt += """Your task:
1. Analyze the repository structure and codebase
2. Understand the problem requirements
3. Implement a solution by modifying the necessary files
4. Ensure your changes are focused and minimal
5. Test your solution if possible

Work within the repository directory and make your changes directly to the files.
When you're done, I will generate a diff of your changes.
"""

        # Track start time for timeout
        start_time = time.time()

        # Use subordinate agent to solve
        delegation = Delegation(
            agent=self.agent,
            name="call_subordinate",
            method=None,
            args={
                'message': solve_prompt,
                'reset': 'true'
            },
            message="Delegating problem solving to subordinate",
            loop_data=None
        )

        # Execute delegation
        response = await delegation.execute()

        # Check timeout
        if time.time() - start_time > timeout:
            return Response(
                message=f"Solution attempt timed out after {timeout} seconds.\n\n{response.message}",
                break_loop=False
            )

        # Generate diff using git_operations_tool
        from python.tools.git_operations_tool import GitOperations

        git_tool = GitOperations(
            agent=self.agent,
            name="git_operations_tool",
            method=None,
            args={
                'operation': 'diff',
                'git_dir': git_dir,
                'base_commit': base_commit
            },
            message="Generating diff",
            loop_data=None
        )

        diff_response = await git_tool.execute()

        # Store diff in agent data
        self.agent.set_data(f"repo_solver_{instance_id}_diff", diff_response.message)

        result = f"""Solution completed.

Agent's work:
{response.message}

Generated diff:
{diff_response.message}
"""

        return Response(message=result, break_loop=False)

    async def _run_tests(self, git_dir: str, instance_id: str) -> Response:
        """Run identified regression tests"""

        # Get test information from agent data
        test_info = self.agent.get_data(f"repo_solver_{instance_id}_tests")

        if not test_info:
            return Response(
                message="Error: No test information found. Run identify_tests first.",
                break_loop=False
            )

        # Use subordinate to run tests
        delegation = Delegation(
            agent=self.agent,
            name="call_subordinate",
            method=None,
            args={
                'message': f"""Run the regression tests identified earlier:

Repository: {git_dir}

Test Information:
{test_info}

Execute the tests and report:
1. Which tests passed
2. Which tests failed
3. Any error messages
4. Overall test results summary""",
                'reset': 'false'  # Continue with same subordinate
            },
            message="Delegating test execution to subordinate",
            loop_data=None
        )

        # Execute delegation
        response = await delegation.execute()

        # Store test results
        self.agent.set_data(f"repo_solver_{instance_id}_test_results", response.message)

        return response

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://engineering Repository Solver: {self.args.get('mode', 'unknown')}",
            content="",
            kvps=self.args,
        )
