from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Literal

from usr.plugins.agent_harness.helpers.models import (
    RunRecord,
    CheckpointRecord,
    RiskLevel,
    now_iso,
    new_id,
    _normalize_path,
    DEPENDENCY_INSTALL_RE,
    DESTRUCTIVE_COMMAND_RE,
)


def get_pending_checkpoint(run: RunRecord) -> CheckpointRecord | None:
    pending = [c for c in run.checkpoints if c.status == "pending"]
    for checkpoint in reversed(pending):
        if checkpoint.status == "pending":
            return checkpoint
    return None


def _is_protected_path(path: str, settings: dict[str, Any]) -> bool:
    normalized = _normalize_path(path)
    basename = Path(path).name
    for pattern in settings.get("protected_paths", []):
        raw_pattern = str(pattern).strip()
        if not raw_pattern:
            continue
        normalized_pattern = _normalize_path(raw_pattern)
        has_glob = any(token in raw_pattern for token in "*?[]")
        looks_like_directory = raw_pattern.endswith("/") or (
            "/" in normalized_pattern and not has_glob and Path(raw_pattern).suffix == ""
        )
        if looks_like_directory:
            directory = normalized_pattern.rstrip("/")
            if normalized == directory or normalized.startswith(normalized_pattern):
                return True
        if fnmatch(normalized, raw_pattern) or fnmatch(basename, raw_pattern):
            return True
    return False


def _terminal_command(tool_name: str, tool_args: dict[str, Any]) -> str:
    if tool_name != "code_execution_tool":
        return ""
    if str(tool_args.get("runtime", "")).lower() != "terminal":
        return ""
    return str(tool_args.get("code", ""))


def _command_matches(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    pattern: re.Pattern[str],
) -> bool:
    command = _terminal_command(tool_name, tool_args)
    return bool(command and pattern.search(command))


def _would_cross_edit_breadth_limit(
    run: RunRecord,
    tool_name: str,
    tool_args: dict[str, Any],
    settings: dict[str, Any],
) -> bool:
    if run.allow_broad_edits:
        return False
    if tool_name != "text_editor":
        return False
    path = str(tool_args.get("path", "")).strip()
    if not path:
        return False
    normalized = _normalize_path(path)
    touched_files = {_normalize_path(item) for item in run.touched_files}
    if normalized in touched_files:
        return False
    return len(touched_files) >= int(settings.get("max_auto_edit_files", 8))


def _set_blocked_state(run: RunRecord, risk_level: RiskLevel) -> None:
    run.phase = "blocked"
    run.status = "blocked"
    run.risk_level = risk_level


def _set_active_state(run: RunRecord) -> None:
    run.phase = "implement" if run.mode != "flash" else "idle"
    run.status = "active"


def request_checkpoint(
    run: RunRecord,
    *,
    reason: str,
    proposed_action: str,
    tool_name: str,
    tool_args: dict[str, Any],
    risk_level: RiskLevel,
) -> CheckpointRecord:
    checkpoint = CheckpointRecord(
        id=new_id("chk"),
        reason=reason,
        proposed_action=proposed_action,
        tool_name=tool_name,
        tool_args=tool_args,
        risk_level=risk_level,
        created_at=now_iso(),
    )
    run.checkpoints.append(checkpoint)
    _set_blocked_state(run, risk_level)
    return checkpoint


def assess_tool_guardrail(
    *,
    run: RunRecord,
    tool_name: str,
    tool_args: dict[str, Any],
    settings: dict[str, Any],
) -> CheckpointRecord | None:
    if tool_name in {"harness_run", "harness_checkpoint", "harness_memory_propose"}:
        return None

    pending = get_pending_checkpoint(run)
    if pending:
        return pending

    if settings.get("dependency_install_requires_checkpoint", True) and _command_matches(
        tool_name=tool_name,
        tool_args=tool_args,
        pattern=DEPENDENCY_INSTALL_RE,
    ):
        return request_checkpoint(
            run,
            reason="Checkpoint required for dependency install in deep harness mode.",
            proposed_action=_terminal_command(tool_name, tool_args).strip(),
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level="high",
        )

    if settings.get("destructive_actions_require_checkpoint", True) and _command_matches(
        tool_name=tool_name,
        tool_args=tool_args,
        pattern=DESTRUCTIVE_COMMAND_RE,
    ):
        return request_checkpoint(
            run,
            reason="Checkpoint required for destructive filesystem or git action.",
            proposed_action=_terminal_command(tool_name, tool_args).strip(),
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level="critical",
        )

    path = str(tool_args.get("path", "")).strip()
    if path and _is_protected_path(path, settings):
        return request_checkpoint(
            run,
            reason=f"Checkpoint required for protected path edit: {Path(path).name}.",
            proposed_action=path,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level="high",
        )

    if _would_cross_edit_breadth_limit(run, tool_name, tool_args, settings):
        return request_checkpoint(
            run,
            reason="Checkpoint required before exceeding the automatic edit breadth limit.",
            proposed_action=path,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level="high",
        )

    return None


def decide_checkpoint(
    run: RunRecord,
    *,
    checkpoint_id: str,
    decision: Literal["approved", "rejected"],
    comment: str = "",
) -> CheckpointRecord:
    for checkpoint in run.checkpoints:
        if checkpoint.id != checkpoint_id:
            continue
        checkpoint.status = decision
        checkpoint.decision_comment = comment
        checkpoint.decided_at = now_iso()
        if decision == "approved":
            _set_active_state(run)
        else:
            _set_blocked_state(run, checkpoint.risk_level)
        return checkpoint
    raise ValueError(f"Checkpoint '{checkpoint_id}' not found")
