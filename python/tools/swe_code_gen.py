from python.helpers.tool import Tool, Response

class SweCodeGen(Tool):
    async def execute(self, **kwargs) -> Response:
        plan_items = self.args.get("plan_items", [])
        write_tests = str(self.args.get("write_tests", "true")).lower().strip() == "true"
        write_docs = str(self.args.get("write_docs", "true")).lower().strip() == "true"

        lines = []
        lines.append("Implementation plan:")
        for i, item in enumerate(plan_items):
            lines.append(f"{i+1}. {item}")

        if write_tests:
            lines.append("Tests: Will add/adjust unit tests near code under test.")
            lines.append("After implementation, will generate a small validation script and run it.")
        if write_docs:
            lines.append("Docs: Will update README/ADR snippets where appropriate.")

        return Response(message="\n".join(lines), break_loop=False)
