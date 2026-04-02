from __future__ import annotations

import re
from typing import Any

from agent import Agent, AgentContext
from usr.plugins.agent_harness.helpers.models import (
    RunRecord,
    TaskRecord,
    VerificationRecord,
    FailureRecord,
    CheckpointRecord,
    MemoryCandidate,
    HarnessMode,
    HarnessPhase,
    RiskLevel,
    VerificationStatus,
    RunStatus,
    now_iso,
    new_id,
    _normalize_path,
    VERIFICATION_COMMAND_RE,
    RUN_CONTEXT_KEY,
    OUTPUT_CONTEXT_KEY,
    DEFAULT_RUN_OBJECTIVE,
    DEFAULT_DEEP_MODE,
    normalize_harness_mode,
)
from usr.plugins.agent_harness.helpers.settings import get_mode_policy, get_default_mode

# --- Structured regex for pytest output parsing (BUG FIX #2) ---

PYTEST_FAILED_RE = re.compile(r"(\d+)\s+failed", re.IGNORECASE)
PYTEST_PASSED_RE = re.compile(r"(\d+)\s+passed", re.IGNORECASE)
PYTEST_ERROR_RE = re.compile(r"(\d+)\s+error", re.IGNORECASE)


def parse_verification_status(output: str) -> VerificationStatus:
    failed_match = PYTEST_FAILED_RE.search(output)
    error_match = PYTEST_ERROR_RE.search(output)
    if failed_match and int(failed_match.group(1)) > 0:
        return "failed"
    if error_match and int(error_match.group(1)) > 0:
        return "failed"
    passed_match = PYTEST_PASSED_RE.search(output)
    if passed_match and int(passed_match.group(1)) > 0:
        return "passed"
    return "unknown"


# --- Phase and risk helpers ---

def _initial_phase_for_mode(mode: HarnessMode) -> HarnessPhase:
    return "idle" if mode == "flash" else "inspect"


def _initial_risk_for_mode(mode: HarnessMode) -> RiskLevel:
    if mode == "ultra":
        return "high"
    if mode in {"standard", "pro"}:
        return "elevated"
    return "low"


# --- Run record creation ---

def create_run_record(
    *,
    context_id: str,
    mode: HarnessMode,
    objective: str,
    constraints: list[str],
    settings: dict[str, Any],
    allow_broad_edits: bool = False,
) -> RunRecord:
    timestamp = now_iso()
    normalized_mode = normalize_harness_mode(mode)
    return RunRecord(
        run_id=new_id("run"),
        context_id=context_id,
        mode=normalized_mode,
        objective=objective.strip() or DEFAULT_RUN_OBJECTIVE,
        constraints=constraints,
        phase=_initial_phase_for_mode(normalized_mode),
        status="active",
        risk_level=_initial_risk_for_mode(normalized_mode),
        allow_broad_edits=allow_broad_edits,
        created_at=timestamp,
        updated_at=timestamp,
    )


# --- Context helpers ---

def _coerce_context(source: AgentContext | Agent) -> AgentContext:
    return source.context if isinstance(source, Agent) else source


def get_current_run(source: AgentContext | Agent) -> RunRecord | None:
    context = _coerce_context(source)
    payload = context.get_data(RUN_CONTEXT_KEY)
    if not payload:
        return None
    return RunRecord.model_validate(payload)


def coerce_constraints(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    return [str(item) for item in items if str(item).strip()]


def ensure_run(
    source: AgentContext | Agent,
    *,
    settings: dict[str, Any],
    mode: HarnessMode | None = None,
    objective: str = DEFAULT_RUN_OBJECTIVE,
    constraints: list[str] | None = None,
    allow_broad_edits: bool = False,
) -> RunRecord:
    run = get_current_run(source)
    if run:
        return run
    context = _coerce_context(source)
    return create_run_record(
        context_id=context.id,
        mode=mode or get_default_mode(settings),
        objective=objective,
        constraints=constraints or [],
        settings=settings,
        allow_broad_edits=allow_broad_edits,
    )


# --- Run state helpers ---

def _set_active_state(run: RunRecord) -> None:
    run.status = "active"
    if run.mode == "flash":
        run.phase = "idle"
    elif run.task_graph and any(
        t.status in ("pending", "dispatched") for t in run.task_graph.sub_tasks
    ):
        run.phase = "implement"
    elif run.phase == "plan" and not run.task_graph:
        pass  # Stay in plan phase if no graph submitted yet
    else:
        run.phase = "implement"


def latest_verification_record(run: RunRecord) -> VerificationRecord | None:
    return run.verification[-1] if run.verification else None


def pending_checkpoints(run: RunRecord) -> list[CheckpointRecord]:
    return [checkpoint for checkpoint in run.checkpoints if checkpoint.status == "pending"]


def proposed_memory_candidates(run: RunRecord) -> list[MemoryCandidate]:
    return [candidate for candidate in run.memory_candidates if candidate.status == "proposed"]


def summarize_run(run: RunRecord) -> dict[str, Any]:
    latest_verification = latest_verification_record(run)
    return {
        "run_id": run.run_id,
        "mode": run.mode,
        "phase": run.phase,
        "status": run.status,
        "risk_level": run.risk_level,
        "objective": run.objective,
        "pending_checkpoints": len(pending_checkpoints(run)),
        "latest_verification": latest_verification.model_dump() if latest_verification else None,
        "memory_candidates": len(proposed_memory_candidates(run)),
    }


def save_current_run(context: AgentContext, run: RunRecord) -> RunRecord:
    run.updated_at = now_iso()
    context.set_data(RUN_CONTEXT_KEY, run.model_dump())
    context.set_output_data(OUTPUT_CONTEXT_KEY, summarize_run(run))
    return run


def clear_current_run(context: AgentContext) -> None:
    context.set_data(RUN_CONTEXT_KEY, None)
    context.set_output_data(OUTPUT_CONTEXT_KEY, None)


def get_pending_checkpoint(run: RunRecord) -> CheckpointRecord | None:
    for checkpoint in reversed(pending_checkpoints(run)):
        if checkpoint.status == "pending":
            return checkpoint
    return None


# --- Run control ---

def stop_run(context: AgentContext) -> None:
    run = get_current_run(context)
    if run:
        try:
            from usr.plugins.agent_harness.helpers.parallel import kill_all
            kill_all(run.run_id)
        except ImportError:
            pass
    clear_current_run(context)


def resume_run(run: RunRecord) -> RunRecord:
    if get_pending_checkpoint(run):
        run.status = "blocked"
        return run
    _set_active_state(run)
    return run


# --- Task management ---

def upsert_task(run: RunRecord, title: str, status: str = "active", details: str = "") -> TaskRecord:
    for task in run.tasks:
        if task.title == title:
            task.status = status
            if details:
                task.details = details
            task.updated_at = now_iso()
            return task
    task = TaskRecord(
        id=new_id("task"),
        title=title,
        status=status,
        details=details,
        updated_at=now_iso(),
    )
    run.tasks.append(task)
    return task


# --- Verification recording (BUG FIX #5: passed -> summarize, not verify) ---

def record_verification(
    run: RunRecord,
    *,
    name: str,
    status: VerificationStatus,
    summary: str,
) -> VerificationRecord:
    record = VerificationRecord(
        id=new_id("verify"),
        name=name,
        status=status,
        summary=summary,
        created_at=now_iso(),
    )
    run.verification.append(record)
    run.phase = "summarize" if status == "passed" else "repair"
    return record


# --- Failure recording ---

def record_failure(
    run: RunRecord,
    *,
    summary: str,
    location: str = "",
    exception_type: str = "",
    settings: dict[str, Any] | None = None,
) -> FailureRecord:
    record = FailureRecord(
        id=new_id("fail"),
        summary=summary,
        location=location,
        exception_type=exception_type,
        created_at=now_iso(),
    )
    run.failures.append(record)
    if run.status != "blocked":
        run.phase = "repair"
    if settings is not None:
        repair_limit = get_mode_policy(settings, run.mode)["repair_limit"]
        if repair_limit >= 0 and len(run.failures) > repair_limit:
            run.phase = "summarize"
    return record


# --- Tool activity recording (BUG FIX #2: structured regex for verification) ---

def record_tool_activity(
    *,
    run: RunRecord,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_response: str = "",
) -> None:
    run.last_tool_name = tool_name
    if tool_name == "text_editor":
        path = str(tool_args.get("path", "")).strip()
        if path:
            normalized = _normalize_path(path)
            if normalized not in {_normalize_path(item) for item in run.touched_files}:
                run.touched_files.append(path)
        if run.status != "blocked":
            run.phase = "implement"
        return

    if tool_name == "call_subordinate":
        title = str(tool_args.get("message", "")).strip() or "Parallel subtask"
        upsert_task(run, title=title[:120], status="completed")
        return

    if tool_name == "code_execution_tool":
        runtime = str(tool_args.get("runtime", "")).lower()
        command = str(tool_args.get("code", "")).strip()
        if VERIFICATION_COMMAND_RE.search(command):
            summary = tool_response.strip().splitlines()[-1] if tool_response.strip() else command
            status = parse_verification_status(tool_response)
            record_verification(run, name=command, status=status, summary=summary)
        elif runtime in {"terminal", "python", "nodejs"} and run.status != "blocked":
            run.phase = "implement"
        return

    if tool_name == "response" and run.status != "blocked":
        # Don't transition to summarize if the task graph has unfinished work
        if run.task_graph and not run.task_graph.is_complete():
            pass  # Stay in implement phase — agent must dispatch remaining tasks
        else:
            run.phase = "summarize"


# --- Run completion ---

def complete_run(run: RunRecord) -> RunRecord:
    if run.status == "blocked":
        return run
    # Auto-mark any remaining pending/dispatched tasks as skipped
    if run.task_graph:
        for task in run.task_graph.sub_tasks:
            if task.status in ("pending", "dispatched"):
                task.status = "completed"
                task.result_summary = "Skipped — agent completed work directly"
                task.completed_at = now_iso()
    run.phase = "complete"
    run.status = "completed"
    run.completed_at = now_iso()
    return run
