from __future__ import annotations

from typing import Any

from usr.plugins.agent_harness.helpers.models import (
    RunRecord, SubTask, TaskGraph, SubTaskRole, now_iso, new_id,
)

VALID_ROLES: set[str] = {"research", "code", "verify", "synthesize"}


def validate_task_graph(graph: TaskGraph) -> list[str]:
    errors: list[str] = []
    ids = {t.id for t in graph.sub_tasks}
    for task in graph.sub_tasks:
        if task.role not in VALID_ROLES:
            errors.append(f"Invalid role '{task.role}' on task '{task.id}'")
        for dep in task.depends_on:
            if dep not in ids:
                errors.append(f"Bad dependency ref '{dep}' on task '{task.id}'")
    if graph.has_cycle():
        errors.append("Task graph contains a cycle")
    return errors


def submit_plan(run: RunRecord, sub_tasks: list[dict[str, Any]]) -> TaskGraph:
    built: list[SubTask] = []
    for idx, raw in enumerate(sub_tasks):
        task_id = f"st_{idx + 1}"
        depends_on_raw = raw.get("depends_on", [])
        depends_on = [f"st_{int(ref) + 1}" for ref in depends_on_raw]
        role = str(raw.get("role", "code")).strip().lower()
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}' for sub-task '{raw.get('title', idx)}'")
        built.append(SubTask(
            id=task_id,
            title=str(raw.get("title", f"Task {idx + 1}")).strip()[:120],
            description=str(raw.get("description", "")).strip(),
            role=role,  # type: ignore[arg-type]
            depends_on=depends_on,
        ))

    graph = TaskGraph(objective=run.objective, sub_tasks=built, created_at=now_iso())

    all_ids = {t.id for t in built}
    for task in built:
        for dep in task.depends_on:
            if dep not in all_ids:
                raise ValueError(f"Bad dependency ref '{dep}' on task '{task.id}'")
    if graph.has_cycle():
        raise ValueError("Task graph contains a cycle")

    run.task_graph = graph
    return graph


def get_ready_tasks(run: RunRecord) -> list[SubTask]:
    if not run.task_graph:
        return []
    return run.task_graph.ready_tasks()


def mark_sub_task_completed(
    run: RunRecord, sub_task_id: str, summary: str = "", files: list[str] | None = None,
) -> SubTask:
    if not run.task_graph:
        raise ValueError("No task graph on run")
    for task in run.task_graph.sub_tasks:
        if task.id == sub_task_id:
            task.status = "completed"
            task.result_summary = summary
            task.result_files = files or []
            task.completed_at = now_iso()
            return task
    raise ValueError(f"Sub-task '{sub_task_id}' not found")


def _cascade_failed_dependencies(run: RunRecord) -> None:
    if not run.task_graph:
        return

    changed = True
    while changed:
        changed = False
        failed_tasks = {task.id: task for task in run.task_graph.sub_tasks if task.status == "failed"}
        for task in run.task_graph.sub_tasks:
            if task.status not in ("pending", "dispatched"):
                continue
            blocking = [failed_tasks[dep] for dep in task.depends_on if dep in failed_tasks]
            if not blocking:
                continue
            dependency_labels = ", ".join(dep.title for dep in blocking)
            task.status = "failed"
            task.result_summary = f"Blocked by failed dependency: {dependency_labels}"
            task.completed_at = now_iso()
            task.dispatched_at = ""
            changed = True


def mark_sub_task_failed(run: RunRecord, sub_task_id: str, error: str = "") -> SubTask:
    if not run.task_graph:
        raise ValueError("No task graph on run")
    for task in run.task_graph.sub_tasks:
        if task.id == sub_task_id:
            task.status = "failed"
            task.result_summary = error
            task.completed_at = now_iso()
            task.dispatched_at = ""
            _cascade_failed_dependencies(run)
            return task
    raise ValueError(f"Sub-task '{sub_task_id}' not found")
