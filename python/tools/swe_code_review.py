from python.helpers.tool import Tool, Response

class SweCodeReview(Tool):
    async def execute(self, **kwargs) -> Response:
        target_paths = self.args.get("target_paths", [])
        ruleset = self.args.get("ruleset", "default")
        max_findings = int(self.args.get("max_findings", 50))

        msg = []
        msg.append(f"Static review (ruleset={ruleset}, max_findings={max_findings})")
        msg.append("Targets:")
        for p in target_paths:
            msg.append(f"- {p}")
        msg.append("Planned checks: style, security hotspots, suspicious patterns, performance pitfalls.")
        msg.append("Next: Provide concrete findings with file:line references after running checks.")
        return Response(message="\n".join(msg), break_loop=False)
