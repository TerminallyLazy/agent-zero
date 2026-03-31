from __future__ import annotations

from typing import Any

from usr.plugins.agent_harness.helpers.models import (
    RunRecord, TokenUsage, CostRecord, now_iso,
)


def record_usage(
    run: RunRecord,
    prompt_tokens: int,
    completion_tokens: int,
    sub_task_id: str = "",
) -> CostRecord:
    if not run.cost:
        run.cost = CostRecord(run_id=run.run_id, updated_at=now_iso())

    run.cost.usage.prompt_tokens += prompt_tokens
    run.cost.usage.completion_tokens += completion_tokens
    run.cost.usage.total_tokens = (
        run.cost.usage.prompt_tokens + run.cost.usage.completion_tokens
    )

    if sub_task_id:
        if sub_task_id not in run.cost.sub_task_usage:
            run.cost.sub_task_usage[sub_task_id] = TokenUsage()
        st_usage = run.cost.sub_task_usage[sub_task_id]
        st_usage.prompt_tokens += prompt_tokens
        st_usage.completion_tokens += completion_tokens
        st_usage.total_tokens = st_usage.prompt_tokens + st_usage.completion_tokens

    run.cost.updated_at = now_iso()
    return run.cost


def check_budget(run: RunRecord, settings: dict[str, Any]) -> bool:
    budget = int(settings.get("token_budget", 0))
    if budget <= 0:
        return False
    if not run.cost:
        return False
    return run.cost.usage.total_tokens >= budget


def render_cost_summary(run: RunRecord) -> str:
    if not run.cost:
        return "No token usage recorded."
    lines = [
        f"Total tokens: {run.cost.usage.total_tokens}",
        f"  Prompt: {run.cost.usage.prompt_tokens}",
        f"  Completion: {run.cost.usage.completion_tokens}",
    ]
    if run.cost.sub_task_usage:
        lines.append("Per sub-task:")
        for task_id, usage in run.cost.sub_task_usage.items():
            lines.append(f"  {task_id}: {usage.total_tokens} tokens")
    return "\n".join(lines)
