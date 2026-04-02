from __future__ import annotations

from helpers.tool import Response, Tool

from usr.plugins.agent_harness.helpers import runtime


def _coerce_risk_level(value: str) -> runtime.RiskLevel:
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "elevated", "high", "critical"}:
        return normalized  # type: ignore[return-value]
    return "high"


class HarnessCheckpoint(Tool):
    async def execute(
        self,
        reason: str = "",
        proposed_action: str = "",
        risk_level: str = "high",
        **kwargs,
    ) -> Response:
        settings = runtime.load_agent_settings(self.agent)
        run = runtime.ensure_run(self.agent, settings=settings)

        existing = runtime.get_pending_checkpoint(run)
        if existing:
            runtime.save_current_run(self.agent.context, run)
            return Response(
                message=(
                    f"Checkpoint already pending: {existing.reason}. "
                    "Wait for user approval before proceeding."
                ),
                break_loop=False,
            )

        checkpoint = runtime.request_checkpoint(
            run,
            reason=str(reason or "Manual checkpoint requested.").strip(),
            proposed_action=str(proposed_action or "Await user approval.").strip(),
            tool_name=self.name,
            tool_args={
                "reason": reason,
                "proposed_action": proposed_action,
                "risk_level": risk_level,
            },
            risk_level=_coerce_risk_level(risk_level),
        )
        runtime.save_current_run(self.agent.context, run)
        return Response(
            message=(
                f"Checkpoint requested: {checkpoint.reason}. "
                "Await user approval before continuing."
            ),
            break_loop=False,
        )
