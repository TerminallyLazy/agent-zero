"""Explicit CAS rollback to a prior staged guidance version."""
from __future__ import annotations

import json

from helpers.api import ApiHandler, Request, Response

from usr.plugins.dspy_rlm.api.status import objective_bucket, required_revision, resolve_context_config
from usr.plugins.dspy_rlm.helpers.promotion import PromotionCoordinator
from usr.plugins.dspy_rlm.helpers import prompt_artifacts


def _json_response(status: int, body: dict) -> Response:
    return Response(json.dumps(body), status=status, mimetype="application/json")


class Rollback(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        context, _cfg, error = resolve_context_config(input)
        if error:
            return error
        assert context is not None
        if input.get("prompt_artifact_id") is not None:
            revision = required_revision(input.get("expected_revision"))
            if revision is None:
                return Response(status=400, response="expected_revision is required", mimetype="text/plain")
            decision = prompt_artifacts.rollback(str(context.id), expected_revision=revision, reason="operator_api")
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
            decision = PromotionCoordinator().rollback(
                str(context.id), bucket, version, expected_revision=revision,
                detail={"source": "api", "action": "explicit_rollback"},
            ).as_dict()
        except ValueError:
            return Response(status=404, response="staged guidance version not found", mimetype="text/plain")
        body = {"plugin": "dspy_rlm", "ok": bool(decision["applied"]), "decision": decision}
        return body if decision["applied"] else _json_response(409, body)
