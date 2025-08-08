from python.helpers.tool import Tool, Response

class SweTesting(Tool):
    async def execute(self, **kwargs) -> Response:
        test_command = self.args.get("test_command", "")
        coverage_command = self.args.get("coverage_command", "")
        install_deps = str(self.args.get("install_deps", "false")).lower().strip() == "true"

        steps = []
        if install_deps:
            steps.append("Prepare: Install dependencies (only if required).")
        if test_command:
            steps.append(f"Run tests: {test_command}")
        if coverage_command:
            steps.append(f"Coverage: {coverage_command}")
        if not steps:
            steps.append("No commands provided. Provide test_command/coverage_command to proceed.")

        return Response(message="\n".join(steps), break_loop=False)
