from __future__ import annotations
import asyncio
import copy
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Coroutine


MAX_RESULT_BYTES = 64 * 1024


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SwarmAgentStatus(str, Enum):
    IDLE = "idle"
    PENDING = "pending"
    WORKING = "working"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {SwarmAgentStatus.DONE, SwarmAgentStatus.FAILED, SwarmAgentStatus.CANCELLED}


class SwarmRunStatus(str, Enum):
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SwarmRun:
    run_id: str
    parent_context_id: str
    parent_agent_name: str
    status: SwarmRunStatus
    started_at: str
    finished_at: str = ""
    title: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "parent_context_id": self.parent_context_id,
            "parent_agent_name": self.parent_agent_name,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "title": self.title,
        }


@dataclass
class SwarmTimelineEvent:
    event_id: str
    run_id: str
    agent_name: str
    kind: str
    text: str
    created_at: str
    ref_id: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "kind": self.kind,
            "text": self.text,
            "created_at": self.created_at,
            "ref_id": self.ref_id,
        }


@dataclass
class SwarmMessage:
    sender: str
    recipient: str
    content: str
    message_id: str = field(default_factory=lambda: f"msg-{uuid.uuid4().hex}")
    run_id: str = ""
    delivery_state: str = "queued"
    timestamp: str = field(default_factory=utc_iso_now)
    created_at: str = ""
    read: bool = False
    delivered_at: str = ""
    failed_at: str = ""
    failure_reason: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = self.timestamp

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "run_id": self.run_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content,
            "delivery_state": self.delivery_state,
            "timestamp": self.timestamp,
            "created_at": self.created_at,
            "read": self.read,
            "delivered_at": self.delivered_at,
            "failed_at": self.failed_at,
            "failure_reason": self.failure_reason,
        }


@dataclass
class SwarmAgent:
    agent_name: str
    label: str
    task: str
    context_id: str
    parent_context_id: str
    status: SwarmAgentStatus
    started_at: str
    current_activity: str = ""
    blocker: str = ""
    result: str = ""
    messages: list[SwarmMessage] = field(default_factory=list)
    finished_at: str = ""
    # Remote enlistment: when these are set, the agent runs on another
    # A0 instance via FastA2A. context_id holds the remote A2A context;
    # remote_task_id is the A2A task id for status polling / cancel.
    remote_label: str = ""
    remote_base_url: str = ""
    remote_task_id: str = ""
    run_id: str = ""
    delivery_mode: str = "local"
    last_seen_at: str = ""
    last_error: str = ""

    @property
    def is_remote(self) -> bool:
        return bool(self.remote_base_url)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "label": self.label,
            "task": self.task,
            "context_id": self.context_id,
            "parent_context_id": self.parent_context_id,
            "status": self.status.value,
            "current_activity": self.current_activity,
            "blocker": self.blocker,
            "result": self.result,
            "messages": [m.to_dict() for m in self.messages],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "remote_label": self.remote_label,
            "remote_base_url": self.remote_base_url,
            "remote_task_id": self.remote_task_id,
            "is_remote": self.is_remote,
            "run_id": self.run_id,
            "delivery_mode": self.delivery_mode,
            "last_seen_at": self.last_seen_at,
            "last_error": self.last_error,
        }


class SwarmRegistry:
    _instance: "SwarmRegistry | None" = None
    _class_lock = threading.Lock()

    def __init__(self) -> None:
        self._agents: dict[str, SwarmAgent] = {}
        self._runs: dict[str, SwarmRun] = {}
        self._messages: dict[str, SwarmMessage] = {}
        self._events: dict[str, SwarmTimelineEvent] = {}
        self._rlock = threading.RLock()
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, Callable[[], Coroutine]]] = []

    @classmethod
    def get(cls) -> "SwarmRegistry":
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, agent: SwarmAgent) -> None:
        with self._rlock:
            if not agent.run_id:
                agent.run_id = self._legacy_run_for_parent(agent.parent_context_id).run_id
            elif agent.run_id not in self._runs:
                self._runs[agent.run_id] = SwarmRun(
                    run_id=agent.run_id,
                    parent_context_id=agent.parent_context_id,
                    parent_agent_name="",
                    status=SwarmRunStatus.ACTIVE,
                    started_at=agent.started_at or utc_iso_now(),
                )
            self._agents[agent.agent_name] = agent
            subs = list(self._subscribers)
        self._fire(subs)

    def create_run(self, parent_context_id: str, parent_agent_name: str = "", title: str = "") -> SwarmRun:
        with self._rlock:
            run = SwarmRun(
                run_id=f"run-{uuid.uuid4().hex}",
                parent_context_id=parent_context_id,
                parent_agent_name=parent_agent_name,
                status=SwarmRunStatus.ACTIVE,
                started_at=utc_iso_now(),
                title=title,
            )
            self._runs[run.run_id] = run
            subs = list(self._subscribers)
        self._fire(subs)
        return copy.deepcopy(run)

    def get_run(self, run_id: str) -> SwarmRun | None:
        with self._rlock:
            return copy.deepcopy(self._runs.get(run_id))

    def add_event(
        self,
        run_id: str,
        agent_name: str,
        kind: str,
        text: str,
        ref_id: str = "",
        event_id: str | None = None,
    ) -> SwarmTimelineEvent:
        with self._rlock:
            if run_id not in self._runs:
                raise ValueError("swarm run does not exist")
            event = SwarmTimelineEvent(
                event_id=event_id or f"evt-{uuid.uuid4().hex}",
                run_id=run_id,
                agent_name=agent_name,
                kind=kind,
                text=text,
                created_at=utc_iso_now(),
                ref_id=ref_id,
            )
            self._events[event.event_id] = event
            subs = list(self._subscribers)
        self._fire(subs)
        return copy.deepcopy(event)

    def create_message(self, run_id: str, sender: str, recipient: str, content: str) -> SwarmMessage:
        with self._rlock:
            target_name = recipient if recipient != "orchestrator" else sender
            target_agent = self._agents.get(target_name)
            if run_id not in self._runs:
                raise ValueError("swarm run does not exist")
            if target_agent is None or target_agent.run_id != run_id:
                raise ValueError("recipient is not in this swarm run")
            sender_agent = None
            if sender != "orchestrator":
                sender_agent = self._agents.get(sender)
                if sender_agent is None:
                    raise ValueError("sender is not in this swarm run")
                if sender_agent.run_id != run_id:
                    raise ValueError("sender is not in this swarm run")
            if recipient != "orchestrator" and sender_agent is not None and sender_agent.run_id != target_agent.run_id:
                raise ValueError("recipient is not in this swarm run")

            msg = SwarmMessage(sender=sender, recipient=recipient, content=content, run_id=run_id)
            self._messages[msg.message_id] = msg
            target_agent.messages.append(msg)
            self._events[f"{msg.message_id}:message"] = SwarmTimelineEvent(
                event_id=f"{msg.message_id}:message",
                run_id=run_id,
                agent_name=target_name,
                kind="message",
                text=content,
                created_at=msg.created_at,
                ref_id=msg.message_id,
            )
            subs = list(self._subscribers)
        self._fire(subs)
        return copy.deepcopy(msg)

    def get_message(self, message_id: str) -> SwarmMessage | None:
        with self._rlock:
            return copy.deepcopy(self._messages.get(message_id))

    def mark_message_delivered(self, message_id: str) -> None:
        self._mark_message_state(message_id, "delivered")

    def mark_message_queued(self, message_id: str) -> None:
        self._mark_message_state(message_id, "queued")

    def mark_message_failed(self, message_id: str, reason: str = "") -> None:
        self._mark_message_state(message_id, "failed", reason)

    def queued_messages_for_agent(self, agent_name: str) -> list[SwarmMessage]:
        with self._rlock:
            return [
                copy.deepcopy(m)
                for m in self._messages.values()
                if m.recipient == agent_name and m.delivery_state == "queued"
            ]

    def messages_for_run(self, run_id: str) -> list[SwarmMessage]:
        with self._rlock:
            return [copy.deepcopy(m) for m in self._messages.values() if m.run_id == run_id]

    def events_for_run(self, run_id: str) -> list[SwarmTimelineEvent]:
        with self._rlock:
            return [copy.deepcopy(e) for e in self._events.values() if e.run_id == run_id]

    def update_status(self, name: str, status: SwarmAgentStatus, **fields) -> None:
        with self._rlock:
            agent = self._agents.get(name)
            if agent is None:
                return
            if agent.status in TERMINAL and status != agent.status:
                return  # absorbing: ignore further writes
            agent.status = status
            for k, v in fields.items():
                if hasattr(agent, k):
                    setattr(agent, k, v)
            if status in TERMINAL and not agent.finished_at:
                agent.finished_at = utc_iso_now()
            subs = list(self._subscribers)
        self._fire(subs)

    def get_agent(self, name: str) -> SwarmAgent | None:
        with self._rlock:
            return self._agents.get(name)

    def update_activity(self, name: str, text: str) -> None:
        with self._rlock:
            agent = self._agents.get(name)
            if agent is None:
                return
            if agent.status in TERMINAL:
                return
            agent.current_activity = text
            subs = list(self._subscribers)
        self._fire(subs)

    def add_message(self, msg: SwarmMessage) -> None:
        with self._rlock:
            target_name = msg.recipient if msg.recipient != "orchestrator" else msg.sender
            agent = self._agents.get(target_name)
            if agent is None:
                return
            if not msg.run_id:
                msg.run_id = agent.run_id
            if msg.run_id in self._runs:
                self._messages[msg.message_id] = msg
                event_id = f"{msg.message_id}:message"
                self._events[event_id] = SwarmTimelineEvent(
                    event_id=event_id,
                    run_id=msg.run_id,
                    agent_name=target_name,
                    kind="message",
                    text=msg.content,
                    created_at=msg.created_at,
                    ref_id=msg.message_id,
                )
            agent.messages.append(msg)
            subs = list(self._subscribers)
        self._fire(subs)

    def get_agent_by_context(self, ctx_id: str) -> SwarmAgent | None:
        with self._rlock:
            for a in self._agents.values():
                if a.context_id == ctx_id:
                    return a
        return None

    def snapshot(self, parent_ctx_id: str | None = None) -> dict:
        with self._rlock:
            agents = list(self._agents.values())
            runs = list(self._runs.values())
            if parent_ctx_id:
                agents = [a for a in agents if a.parent_context_id == parent_ctx_id]
                runs = [r for r in runs if r.parent_context_id == parent_ctx_id]

            flat_agents = [copy.deepcopy(a).to_dict() for a in agents]
            grouped_runs = []
            agent_names = {a.agent_name for a in agents}
            for run in runs:
                run_agents = [a for a in agents if a.run_id == run.run_id]
                run_messages = [
                    m for m in self._messages.values()
                    if m.run_id == run.run_id
                    and (
                        m.recipient in agent_names
                        or m.sender in agent_names
                        or not parent_ctx_id
                    )
                ]
                run_events = [
                    e for e in self._events.values()
                    if e.run_id == run.run_id
                    and (
                        e.agent_name in agent_names
                        or not parent_ctx_id
                    )
                ]
                entry = copy.deepcopy(run).to_dict()
                entry["agents"] = [copy.deepcopy(a).to_dict() for a in run_agents]
                entry["messages"] = [copy.deepcopy(m).to_dict() for m in run_messages]
                entry["timeline"] = [copy.deepcopy(e).to_dict() for e in run_events]
                grouped_runs.append(entry)
            return {"runs": grouped_runs, "agents": flat_agents}

    def remove(self, name: str) -> None:
        with self._rlock:
            agent = self._agents.pop(name, None)
            if agent is not None:
                self._remove_orphaned_run_state(agent.run_id)
            subs = list(self._subscribers)
        self._fire(subs)

    def clear_completed(self, parent_ctx_id: str | None = None) -> None:
        with self._rlock:
            to_remove = [
                n for n, a in self._agents.items()
                if a.status in TERMINAL
                and (parent_ctx_id is None or a.parent_context_id == parent_ctx_id)
            ]
            for n in to_remove:
                agent = self._agents.pop(n)
                self._remove_orphaned_run_state(agent.run_id)
            subs = list(self._subscribers)
        self._fire(subs)

    def clear_for_parent(self, parent_ctx_id: str) -> None:
        with self._rlock:
            to_remove = [n for n, a in self._agents.items() if a.parent_context_id == parent_ctx_id]
            for n in to_remove:
                del self._agents[n]
            run_ids = [r.run_id for r in self._runs.values() if r.parent_context_id == parent_ctx_id]
            for run_id in run_ids:
                self._runs.pop(run_id, None)
            self._messages = {mid: m for mid, m in self._messages.items() if m.run_id not in run_ids}
            self._events = {eid: e for eid, e in self._events.items() if e.run_id not in run_ids}
            subs = list(self._subscribers)
        self._fire(subs)

    def add_subscriber(self, loop: asyncio.AbstractEventLoop, cb: Callable[[], Coroutine]) -> None:
        with self._rlock:
            self._subscribers.append((loop, cb))

    def remove_subscriber(self, cb: Callable[[], Coroutine]) -> None:
        with self._rlock:
            self._subscribers = [(l, c) for (l, c) in self._subscribers if c is not cb]

    def _fire(self, subs: list[tuple[asyncio.AbstractEventLoop, Callable[[], Coroutine]]]) -> None:
        for loop, cb in subs:
            try:
                asyncio.run_coroutine_threadsafe(cb(), loop)
            except Exception:
                pass

    def _legacy_run_for_parent(self, parent_context_id: str) -> SwarmRun:
        for run in self._runs.values():
            if run.parent_context_id == parent_context_id:
                return run
        run = SwarmRun(
            run_id=f"run-{uuid.uuid4().hex}",
            parent_context_id=parent_context_id,
            parent_agent_name="",
            status=SwarmRunStatus.ACTIVE,
            started_at=utc_iso_now(),
        )
        self._runs[run.run_id] = run
        return run

    def _mark_message_state(self, message_id: str, state: str, reason: str = "") -> None:
        with self._rlock:
            msg = self._messages.get(message_id)
            if msg is None:
                return
            msg.delivery_state = state
            if state == "queued":
                msg.delivered_at = ""
                msg.failed_at = ""
                msg.failure_reason = ""
                text = "message queued"
            elif state == "delivered":
                msg.delivered_at = utc_iso_now()
                msg.failed_at = ""
                msg.failure_reason = ""
                text = "message delivered"
            else:
                msg.failed_at = utc_iso_now()
                msg.failure_reason = reason
                text = reason or "message failed"
            target_name = msg.recipient if msg.recipient != "orchestrator" else msg.sender
            event_id = f"{msg.message_id}:delivery:{state}"
            self._events[event_id] = SwarmTimelineEvent(
                event_id=event_id,
                run_id=msg.run_id,
                agent_name=target_name,
                kind="delivery",
                text=text,
                created_at=utc_iso_now(),
                ref_id=msg.message_id,
            )
            subs = list(self._subscribers)
        self._fire(subs)

    def _remove_orphaned_run_state(self, run_id: str) -> None:
        if not run_id:
            return
        if any(a.run_id == run_id for a in self._agents.values()):
            return
        self._runs.pop(run_id, None)
        self._messages = {mid: m for mid, m in self._messages.items() if m.run_id != run_id}
        self._events = {eid: e for eid, e in self._events.items() if e.run_id != run_id}
