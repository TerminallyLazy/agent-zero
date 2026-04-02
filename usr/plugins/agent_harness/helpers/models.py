from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from helpers import files, plugins

PLUGIN_NAME = "agent_harness"
RUN_CONTEXT_KEY = "agent_harness.current_run"
OUTPUT_CONTEXT_KEY = "agent_harness"

HarnessMode = Literal["flash", "standard", "pro", "ultra"]
HarnessPhase = Literal[
    "idle",
    "inspect",
    "plan",
    "implement",
    "verify",
    "repair",
    "blocked",
    "summarize",
    "complete",
]
RiskLevel = Literal["low", "elevated", "high", "critical"]
RunStatus = Literal["active", "blocked", "completed", "stopped"]
CheckpointStatus = Literal["pending", "approved", "rejected"]
MemoryScope = Literal["project", "agent", "global"]
MemoryCandidateStatus = Literal["proposed", "accepted", "rejected"]
VerificationStatus = Literal["passed", "failed", "unknown"]

DEPENDENCY_INSTALL_RE = re.compile(
    r"(^|\s)(pip|pip3|uv\s+pip|npm|pnpm|yarn|poetry|apt|apt-get|brew)\s+"
    r"(install|add)\b",
    re.IGNORECASE,
)
DESTRUCTIVE_COMMAND_RE = re.compile(
    r"(rm\s+-[^\n]*\b[rRfF]+\b|git\s+reset\s+--hard|git\s+checkout\s+--|del\s+/f)",
    re.IGNORECASE,
)
VERIFICATION_COMMAND_RE = re.compile(
    r"\b(pytest|npm\s+test|pnpm\s+test|yarn\s+test|uv\s+run\s+pytest)\b",
    re.IGNORECASE,
)
DEFAULT_RUN_OBJECTIVE = "Active coding task"
DEFAULT_DEEP_MODE: HarnessMode = "pro"
LEGACY_MODE_ALIASES: dict[str, HarnessMode] = {
    "assist": "flash",
    "build": "pro",
    "surge": "ultra",
}


class TaskRecord(BaseModel):
    id: str
    title: str
    status: str = "active"
    details: str = ""
    updated_at: str


class CheckpointRecord(BaseModel):
    id: str
    reason: str
    proposed_action: str
    tool_name: str = ""
    tool_args: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = "high"
    status: CheckpointStatus = "pending"
    decision_comment: str = ""
    sub_task_id: str = ""
    created_at: str
    decided_at: str = ""


class VerificationRecord(BaseModel):
    id: str
    name: str
    status: VerificationStatus
    summary: str
    created_at: str


class FailureRecord(BaseModel):
    id: str
    summary: str
    location: str = ""
    exception_type: str = ""
    created_at: str


class MemoryCandidate(BaseModel):
    id: str
    scope: MemoryScope
    rule_text: str
    reason: str
    source: str
    confidence: float = 0.7
    status: MemoryCandidateStatus = "proposed"
    created_at: str
    decided_at: str = ""


SubTaskRole = Literal["research", "code", "verify", "synthesize"]
SubTaskStatus = Literal["pending", "dispatched", "completed", "failed"]


class SubTask(BaseModel):
    id: str
    title: str
    description: str
    role: SubTaskRole
    depends_on: list[str] = Field(default_factory=list)
    status: SubTaskStatus = "pending"
    result_summary: str = ""
    result_files: list[str] = Field(default_factory=list)
    dispatched_at: str = ""
    completed_at: str = ""


class TaskGraph(BaseModel):
    objective: str
    sub_tasks: list[SubTask] = Field(default_factory=list)
    created_at: str

    def ready_tasks(self) -> list[SubTask]:
        completed = {t.id for t in self.sub_tasks if t.status == "completed"}
        return [
            t for t in self.sub_tasks
            if t.status == "pending"
            and all(dep in completed for dep in t.depends_on)
        ]

    def is_complete(self) -> bool:
        return all(t.status in ("completed", "failed") for t in self.sub_tasks)

    def has_cycle(self) -> bool:
        adj: dict[str, list[str]] = {t.id: list(t.depends_on) for t in self.sub_tasks}
        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            in_stack.add(node)
            for dep in adj.get(node, []):
                if dep in in_stack:
                    return True
                if dep not in visited and dfs(dep):
                    return True
            in_stack.discard(node)
            return False

        return any(dfs(t.id) for t in self.sub_tasks if t.id not in visited)


ContextStatus = Literal["normal", "elevated", "critical"]


class ContextPressure(BaseModel):
    estimated_tokens: int
    threshold_pct: float
    status: ContextStatus
    last_assessed_at: str


class OffloadRecord(BaseModel):
    id: str
    sub_task_id: str = ""
    content_type: str
    file_path: str
    summary: str
    created_at: str


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CostRecord(BaseModel):
    run_id: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    sub_task_usage: dict[str, TokenUsage] = Field(default_factory=dict)
    budget_limit: int = 0
    budget_remaining: int = 0
    updated_at: str


class WorkspacePaths(BaseModel):
    root: str
    workspace: str
    outputs: str
    uploads: str = ""
    offloads: str
    runs: str
    thread_root: str = ""
    user_data: str = ""


class RunRecord(BaseModel):
    run_id: str
    context_id: str
    mode: HarnessMode
    objective: str
    constraints: list[str] = Field(default_factory=list)
    phase: HarnessPhase
    status: RunStatus
    risk_level: RiskLevel
    tasks: list[TaskRecord] = Field(default_factory=list)
    checkpoints: list[CheckpointRecord] = Field(default_factory=list)
    verification: list[VerificationRecord] = Field(default_factory=list)
    failures: list[FailureRecord] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    touched_files: list[str] = Field(default_factory=list)
    allow_broad_edits: bool = False
    last_tool_name: str = ""
    task_graph: TaskGraph | None = None
    offloads: list[OffloadRecord] = Field(default_factory=list)
    cost: CostRecord | None = None
    workspace: WorkspacePaths | None = None
    created_at: str
    updated_at: str
    completed_at: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _normalize_path(path: str) -> str:
    return str(Path(path).as_posix()) if path else ""


def normalize_harness_mode(value: str | None) -> HarnessMode:
    normalized = str(value or "").strip().lower()
    if normalized in {"flash", "standard", "pro", "ultra"}:
        return normalized  # type: ignore[return-value]
    return LEGACY_MODE_ALIASES.get(normalized, DEFAULT_DEEP_MODE)


def _plugin_dir() -> str:
    return plugins.find_plugin_dir(PLUGIN_NAME) or files.get_abs_path(
        files.USER_DIR,
        files.PLUGINS_DIR,
        PLUGIN_NAME,
    )
