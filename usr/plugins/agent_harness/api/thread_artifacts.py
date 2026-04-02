from __future__ import annotations

from flask import send_file

from helpers.api import ApiHandler, Request, Response

from usr.plugins.agent_harness.helpers.deerflow_client import DeerFlowClient


class ThreadArtifacts(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        context_id = (
            request.args.get("context_id")
            or input.get("context_id", "")
        )
        context = self.use_context(str(context_id).strip(), create_if_not_exists=False)
        client = DeerFlowClient(context)

        if request.method == "GET":
            relative_path = str(request.args.get("path", "")).strip()
            artifact = client.resolve_thread_artifact(relative_path)
            if not artifact.exists() or not artifact.is_file():
                return Response("Artifact not found", status=404)
            download = str(request.args.get("download", "1")).strip().lower() not in {
                "0",
                "false",
                "no",
            }
            return send_file(
                artifact,
                as_attachment=download,
                download_name=artifact.name,
            )

        return {
            "success": True,
            "context_id": context.id,
            "artifacts": client.list_thread_artifacts(),
        }
