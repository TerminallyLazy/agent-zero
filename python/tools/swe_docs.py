from python.helpers.tool import Tool, Response

class SweDocs(Tool):
    async def execute(self, **kwargs) -> Response:
        doc_type = self.args.get("doc_type", "api")  # api | adr | deploy | runbook
        target_paths = self.args.get("target_paths", [])
        output_dir = self.args.get("output_dir", "docs")
        fmt = self.args.get("format", "md")

        msg = []
        msg.append(f"Documentation generation: type={doc_type}, format={fmt}, output={output_dir}")
        if target_paths:
            msg.append("Targets:")
            for p in target_paths:
                msg.append(f"- {p}")
        msg.append("Next: Extract APIs/decisions and write concise docs; keep content actionable and minimal.")
        return Response(message="\n".join(msg), break_loop=False)
