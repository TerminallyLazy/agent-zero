from __future__ import annotations
import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Coroutine


MAX_RESULT_BYTES = 64 * 1024


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SwarmAgentStatus(str, Enum):
    PENDING = "pending"
    WORKING = "working"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {SwarmAgentStatus.DONE, SwarmAgentStatus.FAILED, SwarmAgentStatus.CANCELLED}


@dataclass
class SwarmMessage:
    sender: str
    recipient: str
    content: str
    timestamp: str = field(default_factory=utc_iso_now)
    read: bool = False


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
            "messages": [m.__dict__ for m in self.messages],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class SwarmRegistry:
    _instance: "SwarmRegistry | None" = None
    _class_lock = threading.Lock()

    def __init__(self) -> None:
        self._agents: dict[str, SwarmAgent] = {}
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
            self._agents[agent.agent_name] = agent
            subs = list(self._subscribers)
        self._fire(subs)

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

    def _fire(self, subs: list[tuple[asyncio.AbstractEventLoop, Callable[[], Coroutine]]]) -> None:
        for loop, cb in subs:
            try:
                asyncio.run_coroutine_threadsafe(cb(), loop)
            except Exception:
                pass
