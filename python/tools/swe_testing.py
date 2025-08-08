from python.helpers.tool import Tool, Response
from python.tools.code_execution_tool import CodeExecution
import re

class SweTesting(Tool):
    async def execute(self, **kwargs) -> Response:
        install_deps = str(self.args.get("install_deps", "false")).lower().strip() == "true"
        install_command = self.args.get("install_command", "pip install -e .[dev]")
        test_command = self.args.get("test_command", "pytest -q")
        coverage_command = self.args.get("coverage_command", "")
        parse_summary = str(self.args.get("parse_summary", "true")).lower().strip() == "true"
        failures_top_n = int(self.args.get("failures_top_n", 5))

        results = []
        
        if install_deps:
            results.append(f"Installing dependencies: {install_command}")
            args = {"runtime": "terminal", "code": install_command, "session": 0}
            cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
            cet.log = self.get_log_object()
            resp = await cet.execute(**args)
            install_output = resp.message
            if "error" in install_output.lower() or "failed" in install_output.lower():
                results.append("Install failed:")
                results.append(install_output[:500])
                return Response(message="\n".join(results), break_loop=False)
            results.append("Dependencies installed successfully.")

        results.append(f"Running tests: {test_command}")
        args = {"runtime": "terminal", "code": test_command, "session": 0}
        cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
        cet.log = self.get_log_object()
        resp = await cet.execute(**args)
        test_output = resp.message

        if parse_summary:
            lines = test_output.splitlines()
            summary_lines = []
            failure_lines = []
            
            for line in lines:
                if re.search(r"=+ (FAILURES|ERRORS|test session starts)", line, re.IGNORECASE):
                    summary_lines.append(line)
                elif re.search(r"=+ \d+ (failed|passed|skipped|error)", line, re.IGNORECASE):
                    summary_lines.append(line)
                elif re.search(r"FAILED|ERROR", line) and "::" in line:
                    failure_lines.append(line)
            
            if summary_lines:
                results.append("Test summary:")
                results.extend(summary_lines)
            
            if failure_lines:
                results.append(f"Top {failures_top_n} failures:")
                results.extend(failure_lines[:failures_top_n])
                if len(failure_lines) > failures_top_n:
                    results.append(f"... (+{len(failure_lines) - failures_top_n} more failures)")
        else:
            results.append("Raw test output:")
            results.append(test_output[:1000])

        if coverage_command:
            results.append(f"Running coverage: {coverage_command}")
            args = {"runtime": "terminal", "code": coverage_command, "session": 0}
            cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
            cet.log = self.get_log_object()
            resp = await cet.execute(**args)
            coverage_output = resp.message
            
            if parse_summary:
                cov_lines = coverage_output.splitlines()
                for line in cov_lines:
                    if "%" in line and ("TOTAL" in line or "coverage" in line.lower()):
                        results.append(f"Coverage: {line.strip()}")
                        break
            else:
                results.append("Coverage output:")
                results.append(coverage_output[:500])

        return Response(message="\n".join(results), break_loop=False)
