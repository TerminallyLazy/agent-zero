"""Explicit CAS promotion of a staged, context-scoped guidance version."""
from __future__ import annotations

import json

from helpers.api import ApiHandler, Request, Response

from usr.plugins.dspy_rlm.api.status import objective_bucket, required_revision, resolve_context_config
from usr.plugins.dspy_rlm.helpers.promotion import PromotionCoordinator
from usr.plugins.dspy_rlm.helpers import prompt_artifacts


def _json_response(status: int, body: dict) -> Response:
    return Response(json.dumps(body), status=status, mimetype="application/json")


class Promote(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        context, _cfg, error = resolve_context_config(input)
        if error:
            return error
        assert context is not None
        prompt_artifact_id = str(input.get("prompt_artifact_id", "") or "").strip()
        if prompt_artifact_id:
            revision = required_revision(input.get("expected_revision"))
            if revision is None:
                return Response(status=400, response="expected_revision is required", mimetype="text/plain")
            try:
                decision = prompt_artifacts.promote(prompt_artifact_id, expected_revision=revision)
            except ValueError:
                return Response(status=404, response="staged prompt artifact not found", mimetype="text/plain")
            body = {"plugin": "dspy_rlm", "ok": bool(decision.get("applied")), "prompt_decision": decision}
            return body if decision.get("applied") else _json_response(409, body)
        bucket = objective_bucket(input.get("objective_bucket"))
        version = str(input.get("guidance_version", "") or "").strip()
        revision = required_revision(input.get("expected_revision"))
        if bucket is None:
            return Response(status=400, response="known objective_bucket is required", mimetype="text/plain")
        if not version:
            return Response(status=400, response="guidance_version is required", mimetype="text/plain")
        if revision is None:
            return Response(status=400, response="expected_revision is required", mimetype="text/plain")

        try:
            decision = PromotionCoordinator().promote(
                str(context.id), bucket, version, expected_revision=revision,
                detail={"source": "api", "action": "explicit_promote"},
            ).as_dict()
        except ValueError:
            # Do not disclose whether a version exists in another context/bucket.
            return Response(status=404, response="staged guidance version not found", mimetype="text/plain")
        body = {"plugin": "dspy_rlm", "ok": bool(decision["applied"]), "decision": decision}
        return body if decision["applied"] else _json_response(409, body)
