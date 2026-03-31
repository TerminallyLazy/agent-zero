from __future__ import annotations
import inspect
from typing import Any
from agent import Agent, AgentContext
from helpers import plugins
from usr.plugins.agent_harness.helpers.models import (
    MemoryCandidate, MemoryScope, RunRecord, PLUGIN_NAME, now_iso, new_id,
)
from usr.plugins.agent_harness.helpers.settings import (
    load_scope_settings, persist_scope_settings, _merge_unique_rules,
)
from usr.plugins.agent_harness.helpers.lifecycle import (
    get_current_run, save_current_run,
)


def propose_memory_candidate(
    *,
    run: RunRecord,
    rule_text: str,
    reason: str,
    source: str,
    scope: MemoryScope,
    confidence: float,
) -> MemoryCandidate:
    candidate = MemoryCandidate(
        id=new_id("mem"),
        scope=scope,
        rule_text=rule_text.strip(),
        reason=reason.strip(),
        source=source.strip() or PLUGIN_NAME,
        confidence=float(confidence),
        created_at=now_iso(),
    )
    run.memory_candidates.append(candidate)
    return candidate


def find_memory_candidate(run: RunRecord, candidate_id: str) -> MemoryCandidate:
    for candidate in run.memory_candidates:
        if candidate.id == candidate_id:
            return candidate
    raise ValueError(f"Memory candidate '{candidate_id}' not found")


async def maybe_mirror_rule_to_memory(
    *,
    agent: Agent | None,
    candidate: MemoryCandidate,
) -> None:
    if not agent:
        return
    if "_memory" not in plugins.get_enabled_plugins(agent):
        return
    from plugins._memory.helpers.memory import Memory

    memory = await Memory.get(agent)
    await memory.insert_text(
        text=f"Harness rule: {candidate.rule_text}\nReason: {candidate.reason}",
        metadata={
            "area": Memory.Area.MAIN.value,
            "source": PLUGIN_NAME,
            "scope": candidate.scope,
        },
    )


async def accept_memory_candidate(
    *,
    context: AgentContext,
    candidate_id: str,
    scope: MemoryScope,
    project_name: str = "",
    agent_profile: str = "",
) -> MemoryCandidate:
    run = get_current_run(context)
    if not run:
        raise ValueError("No active harness run found")
    candidate = find_memory_candidate(run, candidate_id)
    candidate.status = "accepted"
    candidate.scope = scope
    candidate.decided_at = now_iso()

    scope_settings = load_scope_settings(
        scope=scope,
        project_name=project_name,
        agent_profile=agent_profile,
    )
    accepted_rules = list(scope_settings.get("accepted_rules", []))
    accepted_rules = _merge_unique_rules(
        accepted_rules,
        [
            {
                "scope": scope,
                "rule_text": candidate.rule_text,
                "reason": candidate.reason,
                "source": candidate.source,
                "confidence": candidate.confidence,
                "accepted_at": candidate.decided_at,
            }
        ],
    )
    scope_settings["accepted_rules"] = accepted_rules
    persist_scope_settings(
        scope=scope,
        settings=scope_settings,
        project_name=project_name,
        agent_profile=agent_profile,
    )
    save_current_run(context, run)
    mirror_result = maybe_mirror_rule_to_memory(
        agent=context.get_agent(),
        candidate=candidate,
    )
    if inspect.isawaitable(mirror_result):
        await mirror_result
    return candidate


def reject_memory_candidate(*, run: RunRecord, candidate_id: str) -> MemoryCandidate:
    candidate = find_memory_candidate(run, candidate_id)
    candidate.status = "rejected"
    candidate.decided_at = now_iso()
    return candidate
