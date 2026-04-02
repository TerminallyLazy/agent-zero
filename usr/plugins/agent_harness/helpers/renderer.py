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
    ]

    # Mode-specific workflow instructions
    if run.mode == "ultra":
        prompt.extend([
            "ULTRA WORKFLOW (plan + subagents):",
            "- For simple single-file tasks: implement directly, verify, complete.",
            "- For multi-file tasks (2+ files to create or modify): you MUST plan first.",
            '  Use harness_run action="plan" to decompose into sub-tasks BEFORE writing any code.',
            '  Then use action="dispatch" to spawn parallel sub-agents and action="collect" to harvest results.',
            f"- Up to {policy['subagent_limit']} parallel sub-agents available. USE THEM for independent work.",
            f"- {repair_limit} repair loops max before surfacing the blocker.",
            "- Use harness_checkpoint before: pip/npm install, git push, rm -rf, or editing protected files.",
        ])
    elif run.mode == "pro":
        prompt.extend([
            "PRO WORKFLOW (planned, single-agent):",
            "- Phase 1 INSPECT: Read the repo structure and relevant files. Understand before acting.",
            "- Phase 2 PLAN: Outline the implementation before editing when the task is multi-step or risky.",
            "- Subagents stay disabled in pro mode. Execute the work yourself after planning.",
            "- Phase 3 IMPLEMENT: Make focused changes sequentially.",
            "- Skip dispatch/collect unless you explicitly switch to ultra mode.",
            "- Do NOT use harness_run action=\"plan\" unless you also intend to switch to ultra mode.",
            "- Phase 4 VERIFY: Run tests. Record results with harness_run action=\"verification\".",
            "- Phase 5 COMPLETE: Mark done with harness_run action=\"complete\".",
            f"- {repair_limit} repair loops max before surfacing the blocker.",
            "- MANDATORY checkpoints before: dependency installs, destructive commands, protected file edits, git push.",
            "- Use harness_checkpoint proactively. Do NOT skip checkpoints.",
        ])
    elif run.mode == "standard":
        prompt.extend([
            "STANDARD WORKFLOW (thoughtful single-agent):",
            "- Inspect before editing and keep the work in one agent.",
            "- Planning is optional for simple tasks and recommended for larger ones.",
            "- Subagents stay disabled in standard mode.",
            "- Verify before claiming success.",
        ])
    else:
        prompt.extend([
            "FLASH MODE (fastest path):",
            "- Inspect before editing. Verify before claiming success.",
            "- Skip formal planning unless the task turns out to be larger than expected.",
            "- Subagents stay disabled in flash mode.",
        ])
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

    # Phase-aware task graph sections
    if run.phase in ("inspect", "plan") and not run.task_graph:
        if run.phase == "inspect":
            prompt.extend([
                "INSPECT PHASE — READ BEFORE ACTING",
                "Examine the repo structure, read relevant files, and understand the codebase.",
                'When ready, use harness_run action="phase" phase="plan" to move to planning.',
                "Do NOT start writing code yet.",
            ])
        else:
            prompt.extend([
                "PLANNING PHASE — REQUIRED BEFORE IMPLEMENTING",
                "You MUST decompose the objective into sub-tasks before writing any code.",
                "Each sub-task should be independently executable by a parallel sub-agent.",
                "Available roles: research (read docs/code), code (implement), verify (test), synthesize (combine).",
                "Reference dependencies by index. Example: depends_on: [0] means depends on the first task.",
                'Submit your plan: harness_run action="plan" sub_tasks=[...]',
                "Do NOT use code_execution_tool or text_editor until the plan is submitted.",
            ])

    if run.task_graph:
        completed = [t for t in run.task_graph.sub_tasks if t.status == "completed"]
        dispatched = [t for t in run.task_graph.sub_tasks if t.status == "dispatched"]
        ready = run.task_graph.ready_tasks()
        blocked = [
            t for t in run.task_graph.sub_tasks
            if t.status == "pending" and t not in ready
        ]
        has_remaining = bool(dispatched or ready or blocked)

        graph_lines = [
            "TASK GRAPH STATUS",
            f"Objective: {run.task_graph.objective}",
            f"Progress: {len(completed)}/{len(run.task_graph.sub_tasks)} complete",
        ]
        if completed:
            graph_lines.append(
                "Completed: " + ", ".join(f"{t.title}" for t in completed)
            )
        if dispatched:
            graph_lines.append("In Progress (parallel): " + ", ".join(t.title for t in dispatched))
            graph_lines.append('>>> NEXT ACTION: harness_run action="collect" to harvest results <<<')
        elif ready:
            graph_lines.append("Ready to Dispatch: " + ", ".join(t.title for t in ready))
            graph_lines.append('>>> NEXT ACTION: harness_run action="dispatch" to spawn parallel sub-agents <<<')
        if blocked:
            graph_lines.append("Blocked (waiting on dependencies): " + ", ".join(t.title for t in blocked))

        if has_remaining:
            graph_lines.extend([
                "",
                "!!! WARNING: There are unfinished tasks in the graph. !!!",
                "Do NOT use code_execution_tool or text_editor to implement remaining tasks yourself.",
                "Do NOT use harness_run action=\"complete\" until all tasks are done.",
                "You MUST continue the dispatch → collect cycle until all tasks are completed.",
            ])
            if any(t.status == "failed" for t in run.task_graph.sub_tasks):
                graph_lines.extend([
                    "",
                    "MANUAL TAKEOVER EXCEPTION:",
                    "If sub-agent execution is unavailable or repeatedly failing, you may complete the remaining work yourself.",
                    "After manual completion, reconcile the graph with harness_run action=\"adopt\" for each finished sub-task.",
                ])
        elif completed and not has_remaining:
            graph_lines.append("All sub-tasks complete.")
            graph_lines.append('>>> NEXT ACTION: Run tests to verify, then harness_run action="complete" <<<')
        prompt.extend(graph_lines)

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
    if run.task_graph:
        dispatched = sum(1 for t in run.task_graph.sub_tasks if t.status == "dispatched")
        if dispatched > 0:
            lines.append(f"- parallel_sub_agents: {dispatched} running")
    if run.verification:
        latest = run.verification[-1]
        lines.append(f"- latest_verification: {latest.status} ({latest.summary})")
    return "\n".join(lines)
