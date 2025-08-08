from python.helpers.tool import Tool, Response
from python.helpers import rfc_files
import base64

class SweDocs(Tool):
    async def execute(self, **kwargs) -> Response:
        docs = self.args.get("docs", [])
        default_dir = self.args.get("target_dir", "docs")
        ensure_index = str(self.args.get("ensure_index", "true")).lower().strip() == "true"
        template = self.args.get("template", "")

        results = []
        written = []

        if default_dir:
            rfc_files.make_directories(default_dir)

        if not docs and template:
            if template == "api":
                docs = [{"path": "API.md", "content": "# API\n\nList endpoints/functions and inputs/outputs.\n"}]
            elif template == "adr":
                docs = [{"path": "adr/0001-initial-decision.md", "content": "# ADR: Initial Decision\n\nContext, Decision, Consequences.\n"}]
            elif template == "runbook":
                docs = [{"path": "RUNBOOK.md", "content": "# Runbook\n\nHow to run, test, and deploy the project.\n"}]

        for d in docs:
            path = d.get("path")
            content = d.get("content", "")
            if not path:
                results.append("Skip: missing path")
                continue
            if "/" not in path and default_dir:
                path = f"{default_dir}/{path}"
            parent_dir = "/".join(path.split("/")[:-1]) if "/" in path else ""
            if parent_dir:
                rfc_files.make_directories(parent_dir)
            try:
                b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                ok = rfc_files.write_file_base64(path, b64)
            except Exception as e:
                ok = False
                results.append(f"Write failed: {path} [{str(e)}]")
            status = "ok" if ok else "failed"
            results.append(f"Wrote: {path} [{status}]")
            if ok:
                written.append(path)

        if ensure_index and default_dir:
            index_path = f"{default_dir}/README.md"
            exists = rfc_files.file_exists(index_path)
            if not exists:
                content = "# Documentation\n\nThis directory contains project documentation."
                b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                ok = rfc_files.write_file_base64(index_path, b64)
                status = "ok" if ok else "failed"
                results.append(f"Wrote: {index_path} [{status}]")
                if ok:
                    written.append(index_path)

        results.append("Summary:")
        for p in written:
            results.append(f"- {p}")

        return Response(message="\n".join(results), break_loop=False)
