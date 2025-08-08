from python.helpers.tool import Tool, Response
from python.tools.code_execution_tool import CodeExecution

class SweCodeReview(Tool):
    async def execute(self, **kwargs) -> Response:
        target_paths = self.args.get("target_paths", [])
        ruleset = self.args.get("ruleset", "default")
        max_findings = int(self.args.get("max_findings", 50))
        run = str(self.args.get("run", "true")).lower().strip() == "true"
        include_exts = self.args.get("include_exts", [])
        patterns = self.args.get("patterns", [
            "TODO", "FIXME", "console\\.log\\(", "eval\\(", "password\\s*=",
            "AKIA[0-9A-Z]{16}", "secret", "PRIVATE KEY"
        ])

        if run:
            if not target_paths:
                target_paths = ["."]
            excludes = ["--exclude-dir=.git", "--exclude-dir=node_modules", "--exclude-dir=.venv", "--exclude-dir=venv", "--exclude-dir=dist", "--exclude-dir=build", "--exclude-dir=coverage"]
            rg_excludes = ["-g '!**/.git/**'", "-g '!**/node_modules/**'", "-g '!**/.venv/**'", "-g '!**/venv/**'", "-g '!**/dist/**'", "-g '!**/build/**'", "-g '!**/coverage/**'"]

            cmd_parts = []
            cmd_parts.append("set -e")
            cmd_parts.append("FOUND_RG=$(command -v rg || true)")
            inc_globs = []
            if include_exts:
                for ext in include_exts:
                    ext_clean = str(ext).lstrip(".")
                    inc_globs.append(f"-g '*.{ext_clean}'")

            for pat in patterns:
                if include_exts:
                    rg_cmd = f"rg -n --no-heading {' '.join(rg_excludes + inc_globs)} -e '{pat}'"
                    grep_includes = " ".join([f"--include='*.{str(e).lstrip('.')}'" for e in include_exts])
                    grep_cmd = f"grep -RIn {' '.join(excludes)} {grep_includes} -- '{pat}'"
                else:
                    rg_cmd = f"rg -n --no-heading {' '.join(rg_excludes)} -e '{pat}'"
                    grep_cmd = f"grep -RIn {' '.join(excludes)} -- '{pat}'"

                cmd_parts.append(f"if [ -n \"$FOUND_RG\" ]; then for p in {' '.join(target_paths)}; do {rg_cmd} \"$p\" || true; done; else for p in {' '.join(target_paths)}; do {grep_cmd} \"$p\" || true; done; fi")
            cmd_parts.append("true")
            args = {"runtime": "terminal", "code": " && ".join(cmd_parts), "session": 0}
            cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
            cet.log = self.get_log_object()
            resp = await cet.execute(**args)
            lines = [ln for ln in resp.message.splitlines() if ln.strip()]
            header = [f"Static review (ruleset={ruleset}, max_findings={max_findings})", "Targets:"] + [f"- {p}" for p in target_paths] + ["Findings:"]
            trimmed = lines[:max_findings] if max_findings > 0 else lines
            suffix = []
            if max_findings > 0 and len(lines) > max_findings:
                suffix = [f"(+{len(lines)-max_findings} more)"]
            return Response(message="\n".join(header + trimmed + suffix), break_loop=False)

        msg = []
        msg.append(f"Static review (ruleset={ruleset}, max_findings={max_findings})")
        msg.append("Targets:")
        for p in target_paths:
            msg.append(f"- {p}")
        msg.append("Planned checks: style, security hotspots, suspicious patterns, performance pitfalls.")
        msg.append("Tip: set run='true' to execute non-destructive grep checks via CodeExecution.")
        return Response(message="\n".join(msg), break_loop=False)
