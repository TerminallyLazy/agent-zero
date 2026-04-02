from __future__ import annotations

from helpers import projects
from helpers.tool import Response, Tool

from usr.plugins.agent_harness.helpers import runtime


def _coerce_scope(value: str) -> runtime.MemoryScope:
    normalized = str(value or "").strip().lower()
    if normalized in {"project", "agent", "global"}:
        return normalized  # type: ignore[return-value]
    return "project"


class HarnessMemoryPropose(Tool):
    async def execute(
        self,
        rule_text: str = "",
        reason: str = "",
        scope: str = "project",
        confidence: float = 0.9,
        source: str = runtime.PLUGIN_NAME,
        **kwargs,
    ) -> Response:
        text = str(rule_text or "").strip()
        explanation = str(reason or "").strip()
        if not text:
            return Response(
                message="Memory proposal rejected: 'rule_text' is required.",
                break_loop=False,
            )

        settings = runtime.load_agent_settings(self.agent)
        run = runtime.ensure_run(self.agent, settings=settings)
        normalized_scope = _coerce_scope(scope)

        for existing in run.memory_candidates:
            if existing.rule_text.strip().lower() != text.lower():
                continue
            if existing.status == "proposed":
                runtime.save_current_run(self.agent.context, run)
                return Response(
                    message=f"Memory proposal already pending review: {existing.rule_text}",
                    break_loop=False,
                )

        candidate = runtime.propose_memory_candidate(
            run=run,
            rule_text=text,
            reason=explanation or "Reusable harness rule identified.",
            source=str(source or runtime.PLUGIN_NAME).strip(),
            scope=normalized_scope,
            confidence=float(confidence),
        )
        runtime.save_current_run(self.agent.context, run)

        if not settings.get("memory_curation_enabled", True):
            project_name = projects.get_context_project_name(self.agent.context) or ""
            agent_profile = self.agent.config.profile or ""
            accepted = await runtime.accept_memory_candidate(
                context=self.agent.context,
                candidate_id=candidate.id,
                scope=normalized_scope,
                project_name=project_name,
                agent_profile=agent_profile,
            )
            return Response(
                message=f"Harness memory saved: {accepted.rule_text}",
                break_loop=False,
            )

        return Response(
            message=f"Memory proposal queued for review: {candidate.rule_text}",
            break_loop=False,
        )
