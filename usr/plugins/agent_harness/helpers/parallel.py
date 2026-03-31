from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from agent import Agent, AgentContext, AgentContextType, UserMessage
from helpers.defer import DeferredTask
from initialize import initialize_agent

from usr.plugins.agent_harness.helpers.models import (
    RunRecord, SubTask, now_iso,
)
from usr.plugins.agent_harness.helpers.orchestrator import build_scoped_context

# Module-level registry of active background sub-agents.
# DeferredTask objects are not serializable, so they live here instead of on RunRecord.
_active_tasks: dict[str, "BackgroundSubAgent"] = {}
_lock = threading.Lock()


@dataclass
class BackgroundSubAgent:
    sub_task_id: str
    run_id: str
    context: AgentContext
    agent: Agent
    deferred: DeferredTask
    spawned_at: str = field(default_factory=now_iso)


def spawn_parallel(
    run: RunRecord,
    sub_tasks: list[SubTask],
    settings: dict[str, Any],
) -> list[str]:
    """Spawn background agents for each sub-task. Returns list of spawned IDs."""
    spawned_ids: list[str] = []
    for sub_task in sub_tasks:
        scoped_msg = build_scoped_context(sub_task, run)

        # Create an isolated background context and agent
        config = initialize_agent()
        ctx = AgentContext(
            config=config,
            type=AgentContextType.BACKGROUND,
            set_current=False,
        )
        agent = ctx.agent0

        # Seed the agent with the scoped task context
        agent.hist_add_user_message(
            UserMessage(message=scoped_msg, attachments=[])
        )

        # Spawn the monologue in a background thread
        thread_name = f"harness-{run.run_id}-{sub_task.id}"
        deferred = DeferredTask(thread_name=thread_name)
        deferred.start_task(agent.monologue)

        bg = BackgroundSubAgent(
            sub_task_id=sub_task.id,
            run_id=run.run_id,
            context=ctx,
            agent=agent,
            deferred=deferred,
        )

        with _lock:
            _active_tasks[sub_task.id] = bg

        # Mark the sub-task as dispatched
        sub_task.status = "dispatched"
        sub_task.dispatched_at = now_iso()
        spawned_ids.append(sub_task.id)

    return spawned_ids


def poll_status(run_id: str) -> dict[str, str]:
    """Check each active background task for a given run.
    Returns dict of sub_task_id -> 'running' | 'completed' | 'failed'.
    """
    results: dict[str, str] = {}
    with _lock:
        for task_id, bg in list(_active_tasks.items()):
            if bg.run_id != run_id:
                continue
            if not bg.deferred.is_ready():
                results[task_id] = "running"
            else:
                try:
                    bg.deferred.result_sync(timeout=0)
                    results[task_id] = "completed"
                except Exception:
                    results[task_id] = "failed"
    return results


def collect_completed(run: RunRecord) -> list[tuple[str, str | None, str | None]]:
    """Harvest results from finished background tasks.
    Returns list of (sub_task_id, summary_or_none, error_or_none).
    Removes completed/failed tasks from the registry.
    """
    collected: list[tuple[str, str | None, str | None]] = []
    to_remove: list[str] = []

    with _lock:
        for task_id, bg in list(_active_tasks.items()):
            if bg.run_id != run.run_id:
                continue
            if not bg.deferred.is_ready():
                continue

            try:
                result = bg.deferred.result_sync(timeout=0)
                summary = str(result)[:500] if result else ""
                collected.append((task_id, summary, None))
            except Exception as exc:
                collected.append((task_id, None, str(exc)))
            to_remove.append(task_id)

        for task_id in to_remove:
            _active_tasks.pop(task_id, None)

    return collected


def kill_all(run_id: str) -> int:
    """Kill all background tasks for a run. Returns number killed."""
    killed = 0
    with _lock:
        to_remove = [
            task_id for task_id, bg in _active_tasks.items()
            if bg.run_id == run_id
        ]
        for task_id in to_remove:
            bg = _active_tasks.pop(task_id)
            try:
                bg.deferred.kill()
            except Exception:
                pass
            killed += 1
    return killed


def active_count(run_id: str) -> int:
    """Return number of currently running background tasks for a run."""
    with _lock:
        return sum(
            1 for bg in _active_tasks.values()
            if bg.run_id == run_id and not bg.deferred.is_ready()
        )
