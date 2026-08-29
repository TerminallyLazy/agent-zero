"""Queue-only manual optimization endpoint."""
from __future__ import annotations

from helpers.api import ApiHandler, Request, Response

from usr.plugins.dspy_rlm.api.status import public_config, public_context_state, resolve_context_config
from usr.plugins.dspy_rlm.helpers.runtime_policy import RuntimePolicy


class Optimize(ApiHandler):
    """Validate a live context and enqueue work; this request never runs a worker."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        context, cfg, error = resolve_context_config(input)
        if error:
            return error
        assert context is not None and cfg is not None

        force = input.get("force", False)
        if not isinstance(force, bool):
            return Response(status=400, response="force must be a boolean", mimetype="text/plain")
        policy = RuntimePolicy.from_config(cfg)
        reasons = policy.reasons_for("optimize", force=force)
        if reasons:
            return {
                "plugin": "dspy_rlm",
                "ok": False,
                "context_id": str(context.id),
                "result": {"status": "skipped", "reason": reasons[0], "reasons": list(reasons)},
                "config": public_config(cfg),
                "worker_operation": {"mode": "local_multiprocess", "request_execution": "queue_only"},
            }

        from usr.plugins.dspy_rlm.helpers import _scheduler_coordinator as scheduler
        from usr.plugins.dspy_rlm.helpers import state
        from usr.plugins.dspy_rlm.helpers.worker_supervisor import reconcile

        queued = scheduler.schedule_optimization_job(context_id=str(context.id), cfg=cfg, force=force)
        workers = reconcile(cfg) if queued.get("dispatched", False) else {}
        return {
            "plugin": "dspy_rlm",
            "ok": bool(queued.get("dispatched", False)),
            "context_id": str(context.id),
            "scheduler": queued,
            "context_state": public_context_state(state.load_context_state(str(context.id))),
            "config": public_config(cfg),
            "worker_operation": {
                "mode": "local_multiprocess",
                "request_execution": "queue_only",
                "workers": workers,
                "operator_command": "python3 -m usr.plugins.dspy_rlm.worker --once",
            },
        }
