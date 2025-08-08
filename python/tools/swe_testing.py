from python.helpers.tool import Tool, Response
from python.tools.code_execution_tool import CodeExecution
import re

class SweTesting(Tool):
    async def execute(self, **kwargs) -> Response:
        test_command = self.args.get("test_command", "")
        coverage_command = self.args.get("coverage_command", "")
        install_deps = str(self.args.get("install_deps", "false")).lower().strip() == "true"
        install_command = self.args.get("install_command", "")
        parse_summary = str(self.args.get("parse_summary", "true")).lower().strip() == "true"
        failures_top_n = int(self.args.get("failures_top_n", 5))

        steps = []
        cmds = []

        if install_deps and install_command:
            steps.append(f"Prepare: {install_command}")
            cmds.append(install_command)

        if test_command:
            steps.append(f"Run tests: {test_command}")
            cmds.append(test_command)

        if coverage_command:
            steps.append(f"Coverage: {coverage_command}")
            cmds.append(coverage_command)

        if not steps:
            steps.append("No commands provided. Provide test_command/coverage_command to proceed.")
            return Response(message="\n".join(steps), break_loop=False)

        args = {"runtime": "terminal", "code": " && ".join(cmds), "session": 0}
        cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
        cet.log = self.get_log_object()
        resp = await cet.execute(**args)

        if not parse_summary:
            return Response(message=resp.message, break_loop=False)

        lines = resp.message.splitlines()
        summary = []
        pytest_summary = []
        coverage_summary = []
        failure_lines = []

        for ln in lines:
            s = ln.strip()
            if (" failed" in s or " passed" in s or " error" in s) and ("pytest" in "pytest" or "collected" in s or s.endswith("in")):
                if re.search(r"(failed|passed|errors|xfailed|skipped)", s, re.IGNORECASE):
                    pytest_summary.append(s)
            if re.search(r"TOTAL.+\d+%|\bCoverage\b.+\d+%", s):
                coverage_summary.append(s)
            if re.search(r":\d+:\s*(AssertionError|E\s+|FAILED|ERROR)", s):
                failure_lines.append(s)
            elif re.search(r"^\s*E\s", s):
                failure_lines.append(s)

        summary.append("Test execution summary:")
        if pytest_summary:
            summary.append("Pytest summary:")
            summary.extend(pytest_summary[:3])
        if coverage_summary:
            summary.append("Coverage summary:")
            summary.extend(coverage_summary[:3])
        if failure_lines:
            summary.append(f"Top {min(failures_top_n, len(failure_lines))} failure lines:")
            summary.extend(failure_lines[:failures_top_n])

        return Response(message="\n".join(summary) if summary else resp.message, break_loop=False)
