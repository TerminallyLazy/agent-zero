from __future__ import annotations

from typing import Any

from usr.plugins.agent_harness.helpers.models import (
    RunRecord, ContextPressure, OffloadRecord, ContextStatus, now_iso, new_id,
)
from usr.plugins.agent_harness.helpers.workspace import write_offload


def assess_pressure_from_tokens(
    estimated_tokens: int, settings: dict[str, Any],
) -> ContextPressure:
    threshold = float(settings.get("context_pressure_threshold", 0.7))
    window = int(settings.get("context_model_window", 128000))
    ratio = estimated_tokens / window if window > 0 else 0.0

    status: ContextStatus
    if ratio >= 0.9:
        status = "critical"
    elif ratio >= threshold:
        status = "elevated"
    else:
        status = "normal"

    return ContextPressure(
        estimated_tokens=estimated_tokens,
        threshold_pct=threshold,
        status=status,
        last_assessed_at=now_iso(),
    )


def should_offload(pressure: ContextPressure) -> bool:
    return pressure.status in ("elevated", "critical")


def offload_content(
    run: RunRecord,
    content: str,
    content_type: str,
    sub_task_id: str = "",
) -> OffloadRecord:
    offload_id = new_id("off")
    file_path = ""
    if run.workspace:
        file_path = write_offload(run.workspace, offload_id, content)

    summary = content[:100].replace("\n", " ").strip()
    if len(content) > 100:
        summary += "..."

    record = OffloadRecord(
        id=offload_id,
        sub_task_id=sub_task_id,
        content_type=content_type,
        file_path=file_path,
        summary=summary,
        created_at=now_iso(),
    )
    run.offloads.append(record)
    return record


def render_offload_summaries(run: RunRecord) -> str:
    if not run.offloads:
        return ""
    lines = ["Offloaded content (read files for full details):"]
    for rec in run.offloads:
        lines.append(f"- [{rec.content_type}] {rec.summary} -> {rec.file_path}")
    return "\n".join(lines)
