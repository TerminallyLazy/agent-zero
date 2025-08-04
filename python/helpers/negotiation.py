import uuid
from enum import Enum
from typing import Dict, Any
from datetime import datetime, timezone

def time_iso():
    return datetime.now(timezone.utc).isoformat()

class TaskState(Enum):
    PROPOSED = "proposed"
    CLARIFYING = "clarifying"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

def make_task_envelope(
    initiator_id: str,
    goal: str,
    context_snippets: Dict[str, Any],
    required_capabilities: Dict[str, bool],
    response_channel: str,
) -> Dict[str, Any]:
    return {
        "task_id": str(uuid.uuid4()),
        "initiator": initiator_id,
        "goal": goal,
        "context": context_snippets,
        "required_capabilities": required_capabilities,
        "response_channel": response_channel,
        "state": TaskState.PROPOSED.value,
        "history": [],
        "created_at": time_iso(),
    }

def propose(task: Dict[str, Any]) -> None:
    task["state"] = TaskState.PROPOSED.value
    task["history"].append({"event": "proposed", "timestamp": time_iso()})

def request_clarification(task: Dict[str, Any], question: str) -> None:
    task["state"] = TaskState.CLARIFYING.value
    task["history"].append({"event": "clarification_requested", "detail": question, "timestamp": time_iso()})

def accept(task: Dict[str, Any], modifications: Dict[str, Any] = None) -> None:
    task["state"] = TaskState.ACCEPTED.value
    task["history"].append({"event": "accepted", "modifications": modifications or {}, "timestamp": time_iso()})

def reject(task: Dict[str, Any], reason: str) -> None:
    task["state"] = TaskState.REJECTED.value
    task["history"].append({"event": "rejected", "reason": reason, "timestamp": time_iso()})

def update_progress(task: Dict[str, Any], progress: str) -> None:
    task["history"].append({"event": "progress", "detail": progress, "timestamp": time_iso()})

def complete(task: Dict[str, Any], result: Any) -> None:
    task["state"] = TaskState.COMPLETED.value
    task["result"] = result
    task["history"].append({"event": "completed", "timestamp": time_iso()})