from python.helpers.tool import Tool, Response
from python.tools.code_execution_tool import CodeExecution

class SweCodeReview(Tool):
    async def execute(self, **kwargs) -> Response:
        target_paths = self.args.get("target_paths", [])
        ruleset = self.args.get("ruleset", "default")
        max_findings = int(self.args.get("max_findings", 50))
        run = str(self.args.get("run", "true")).lower().strip() == "true"
        patterns = self.args.get("patterns", [
            "TODO", "FIXME", "console\\.log\\(", "eval\\(", "password\\s*=",
            "AKIA[0-9A-Z]{16}", "secret", "PRIVATE KEY"
        ])

        if run:
            if not target_paths:
                target_paths = ["."]
            cmd_parts = []
            cmd_parts.append("set -e")
            cmd_parts.append("FINDINGS=0")
            cmd_parts.append("FOUND_FILE=$(command -v rg || true)")
            for pat in patterns:
                cmd_parts.append(f"if [ -n \"$FOUND_FILE\" ]; then for p in {' '.join(target_paths)}; do rg -n --no-heading -e '{pat}' \"$p\" || true; done; else for p in {' '.join(target_paths)}; do grep -RIn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=venv -- '{pat}' \"$p\" || true; done; fi")
            cmd_parts.append("true")  # ensure non-failing
            args = {"runtime": "terminal", "code": " && ".join(cmd_parts), "session": 0}
            cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
            cet.log = self.get_log_object()
            resp = await cet.execute(**args)
            lines = resp.message.splitlines()
            header = [f"Static review (ruleset={ruleset}, max_findings={max_findings})", "Targets:"] + [f"- {p}" for p in target_paths] + ["Findings:"]
            trimmed = lines[:max_findings] if max_findings > 0 else lines
            return Response(message="\n".join(header + trimmed), break_loop=False)

        msg = []
        msg.append(f"Static review (ruleset={ruleset}, max_findings={max_findings})")
        msg.append("Targets:")
        for p in target_paths:
            msg.append(f"- {p}")
        msg.append("Planned checks: style, security hotspots, suspicious patterns, performance pitfalls.")
        msg.append("Tip: set run='true' to execute non-destructive grep checks via CodeExecution.")
        return Response(message="\n".join(msg), break_loop=False)
