from __future__ import annotations

from helpers.api import ApiHandler, Request, Response
from helpers.security import safe_filename

from usr.plugins.agent_harness.helpers.deerflow_client import DeerFlowClient


class ThreadUploads(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = (
            request.args.get("action")
            or request.form.get("action")
            or input.get("action", "list")
        )
        action = str(action or "list").strip().lower()
        context_id = (
            request.args.get("context_id")
            or request.form.get("context_id")
            or input.get("context_id", "")
        )
        context = self.use_context(str(context_id).strip(), create_if_not_exists=False)
        client = DeerFlowClient(context)

        if action == "delete":
            relative_path = str(
                request.form.get("path") or input.get("path") or input.get("filename", "")
            ).strip()
            deleted = client.delete_thread_upload(relative_path)
            return {
                "success": deleted,
                "context_id": context.id,
                "uploads": client.list_thread_uploads(),
            }

        if action == "upload":
            files_to_save = request.files.getlist("files[]") or request.files.getlist("file")
            if not files_to_save:
                files_to_save = list(request.files.values())
            if not files_to_save:
                return {
                    "success": False,
                    "context_id": context.id,
                    "error": "No files uploaded",
                    "uploads": client.list_thread_uploads(),
                }

            saved: list[str] = []
            skipped: list[str] = []
            for file in files_to_save:
                if not file or not file.filename:
                    continue
                filename = safe_filename(file.filename)
                if not filename:
                    skipped.append(file.filename)
                    continue
                client.save_thread_upload(filename, file.read())
                saved.append(filename)

            return {
                "success": True,
                "context_id": context.id,
                "saved": saved,
                "skipped": skipped,
                "uploads": client.list_thread_uploads(),
            }

        return {
            "success": True,
            "context_id": context.id,
            "uploads": client.list_thread_uploads(),
        }
