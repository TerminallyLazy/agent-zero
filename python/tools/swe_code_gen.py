from python.helpers.tool import Tool, Response
from python.helpers import rfc_files
from python.tools.code_execution_tool import CodeExecution
import base64

class SweCodeGen(Tool):
    async def execute(self, **kwargs) -> Response:
        plan_items = self.args.get("plan_items", [])
        files = self.args.get("files", [])
        write_tests = str(self.args.get("write_tests", "true")).lower().strip() == "true"
        write_docs = str(self.args.get("write_docs", "true")).lower().strip() == "true"
        create_validation = str(self.args.get("create_validation", "true")).lower().strip() == "true"
        run_validation = str(self.args.get("run_validation", "true")).lower().strip() == "true"
        validation_path = self.args.get("validation_path", "scripts/validate_swe_changes.py")
        validation_code = self.args.get("validation_code", "")
        validation_cmd = self.args.get("validation_cmd", "")
        dry_run = str(self.args.get("dry_run", "false")).lower().strip() == "true"

        results = []
        results.append("Implementation plan:")
        for i, item in enumerate(plan_items):
            results.append(f"{i+1}. {item}")

        written_paths = []

        for f in files:
            path = f.get("path")
            content = f.get("content", "")
            if not path:
                results.append("Skip: missing file path")
                continue
            if dry_run:
                results.append(f"Planned write: {path} [{len(content.encode('utf-8'))} bytes]")
                continue
            b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            parent_dir = "/".join(path.split("/")[:-1]) if "/" in path else ""
            if parent_dir:
                rfc_files.make_directories(parent_dir)
            try:
                ok = rfc_files.write_file_base64(path, b64)
            except Exception as e:
                ok = False
                results.append(f"Write failed: {path} [{str(e)}]")
            status = "ok" if ok else "failed"
            results.append(f"Wrote: {path} [{status}]")
            if ok:
                written_paths.append(path)

        if write_tests:
            results.append("Tests: ensure unit tests updated near code under test.")

        if write_docs:
            results.append("Docs: remember to update README/ADR where appropriate.")

        validation_output = ""
        if create_validation:
            if dry_run:
                results.append(f"Planned validation script: {validation_path}")
            else:
                if not validation_code:
                    validation_code = (
                        "import sys\n"
                        "print('Validation: basic check passed (placeholder).')\n"
                    )
                parent_dir = "/".join(validation_path.split("/")[:-1]) if "/" in validation_path else ""
                if parent_dir:
                    rfc_files.make_directories(parent_dir)
                vb64 = base64.b64encode(validation_code.encode('utf-8')).decode('utf-8')
                rfc_files.write_file_base64(validation_path, vb64)
                results.append(f"Wrote validation script: {validation_path}")
                written_paths.append(validation_path)

                if run_validation:
                    cmd = validation_cmd or f"python {validation_path}"
                    args = {"runtime": "terminal", "code": cmd, "session": 0}
                    cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
                    cet.log = self.get_log_object()
                    resp = await cet.execute(**args)
                    validation_output = resp.message
                    results.append("Validation output:")
                    results.append(validation_output.strip())

        return Response(message="\n".join(results), break_loop=False)
