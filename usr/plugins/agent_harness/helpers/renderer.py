from __future__ import annotations
from typing import Any
from usr.plugins.agent_harness.helpers.models import RunRecord
from usr.plugins.agent_harness.helpers.settings import get_mode_policy
from usr.plugins.agent_harness.helpers.lifecycle import get_pending_checkpoint


def render_system_prompt(
    *,
    settings: dict[str, Any],
    run: RunRecord | None,
    accepted_rules: list[dict[str, Any]],
) -> str:
    rules_text = "\n".join(
        f"- {rule.get('rule_text', '').strip()}"
        for rule in accepted_rules
        if str(rule.get("rule_text", "")).strip()
    )

    if run is None:
        if not settings.get("ambient_assist_enabled", True):
            return ""
        prompt = [
            "AGENT HARNESS AMBIENT ASSIST",
            "You are in coding-first assist mode.",
            "Inspect the repo before editing, complete implementation requests end-to-end when safe, and verify work before claiming success.",
        ]
        if rules_text:
            prompt.extend(["Accepted project rules:", rules_text])
        return "\n\n".join(prompt)

    policy = get_mode_policy(settings, run.mode)
    pending = get_pending_checkpoint(run)
    repair_limit = policy["repair_limit"]
    prompt = [
        f"AGENT HARNESS {run.mode.upper()} MODE",
        f"Objective: {run.objective}",
        f"Current phase: {run.phase}",
        f"Run status: {run.status}",
        f"Risk level: {run.risk_level}",
        "Deep harness behavior:",
        "- Continue through inspect, implement, verify, and repair by default instead of stopping at analysis.",
        f"- max {policy['subagent_limit']} concurrent subagents in this mode.",
        f"- max {repair_limit} bounded repair loops before surfacing a blocker.",
        "- Prefer composing existing Agent Zero tools and plugins over inventing alternate workflows.",
    ]
    if run.constraints:
        prompt.extend(["Constraints:", "\n".join(f"- {item}" for item in run.constraints)])
    if pending:
        prompt.extend(
            [
                "Checkpoint state:",
                f"- Pending checkpoint: {pending.reason}",
                f"- Proposed action: {pending.proposed_action}",
                "- Do not continue with risky actions until the checkpoint is resolved.",
            ]
        )
    if repair_limit >= 0 and len(run.failures) > repair_limit:
        prompt.extend(
            [
                "Repair budget state:",
                f"- bounded repair budget exhausted after {repair_limit} repair loops.",
                "- Stop retrying blindly, summarize the blocker clearly, and surface the best next action.",
            ]
        )
    if rules_text:
        prompt.extend(["Accepted rules:", rules_text])
    return "\n\n".join(prompt)


def render_runtime_summary(run: RunRecord | None) -> str:
    if run is None:
        return ""
    lines = [
        "# Harness runtime",
        f"- mode: {run.mode}",
        f"- phase: {run.phase}",
        f"- status: {run.status}",
        f"- objective: {run.objective}",
    ]
    pending = get_pending_checkpoint(run)
    if pending:
        lines.append(f"- pending_checkpoint: {pending.reason}")
    if run.verification:
        latest = run.verification[-1]
        lines.append(f"- latest_verification: {latest.status} ({latest.summary})")
    return "\n".join(lines)
