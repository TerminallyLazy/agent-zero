from python.helpers.tool import Tool, Response
from python.tools.code_execution_tool import CodeExecution

class SweRepoAnalysis(Tool):
    async def execute(self, **kwargs) -> Response:
        target_path = str(self.args.get("target_path", "."))
        analysis_depth = str(self.args.get("analysis_depth", "shallow"))
        generate_summary = str(self.args.get("generate_summary", "false")).lower().strip() == "true"
        run = str(self.args.get("run", "false")).lower().strip() == "true"

        if run:
            cmd = []
            cmd.append(f'cd {target_path}')
            cmd.append('pwd')
            cmd.append('ls -1')
            cmd.append('[ -f README.md ] && echo "README.md found" || true')
            cmd.append('[ -f pyproject.toml ] && echo "pyproject.toml found" || true')
            cmd.append('[ -f requirements.txt ] && echo "requirements.txt found" || true')
            cmd.append('[ -f package.json ] && echo "package.json found" || true')
            cmd.append('[ -d tests ] && echo "tests/ found" || true')
            cmd.append('[ -d src ] && echo "src/ found" || true')
            if analysis_depth.lower() in ("medium", "deep"):
                cmd.append('find . -maxdepth 2 -type d -printf "%p\\n" | sort')
            args = {"runtime": "terminal", "code": " && ".join(cmd), "session": 0}
            cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
            cet.log = self.get_log_object()
            resp = await cet.execute(**args)
            return Response(message=resp.message, break_loop=False)

        summary = []
        summary.append(f"Target: {target_path}")
        summary.append(f"Depth: {analysis_depth}")
        summary.append("Actions:")
        summary.append("- Inspect repository layout and common files (README, package/pyproject, tests)")
        summary.append("- Identify primary languages and dependency manifests")
        summary.append("- Detect test frameworks and CI configs")
        summary.append("- Outline key modules and probable data flows")
        if generate_summary:
            summary.append("- Prepare a concise JSON/markdown summary for later tools")

        msg = "\n".join(summary)
        return Response(message=msg, break_loop=False)
