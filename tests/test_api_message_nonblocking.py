from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.api_message import ApiMessage


class _FakeTask:
    def __init__(self) -> None:
        self.awaited = False

    async def result(self) -> str:
        self.awaited = True
        raise AssertionError("Non-blocking API path should not await the agent result.")


class _FakeLog:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


class _FakeContext:
    def __init__(self, context_id: str = "ctx-nonblocking") -> None:
        self.id = context_id
        self.log = _FakeLog()
        self._data: dict[str, object] = {}
        self.task = _FakeTask()

    def get_data(self, key: str):
        return self._data.get(key)

    def communicate(self, _message):
        return self.task


class _FakeAgentContext:
    created: list[_FakeContext] = []
    stored: dict[str, _FakeContext] = {}

    def __new__(cls, *args, **kwargs):
        context = _FakeContext()
        cls.created.append(context)
        cls.stored[context.id] = context
        return context

    @classmethod
    def use(cls, context_id: str):
        return cls.stored.get(context_id)

    @classmethod
    def get(cls, context_id: str):
        return cls.stored.get(context_id)

    @classmethod
    def remove(cls, context_id: str):
        cls.stored.pop(context_id, None)


def test_api_message_can_return_before_agent_finishes(monkeypatch) -> None:
    _FakeAgentContext.created.clear()
    _FakeAgentContext.stored.clear()

    monkeypatch.setattr("api.api_message.AgentContext", _FakeAgentContext)
    monkeypatch.setattr("api.api_message.initialize_agent", lambda override_settings=None: object())
    monkeypatch.setattr("api.api_message.activate_project", lambda *args, **kwargs: None)
    monkeypatch.setattr("api.api_message.projects.activate_project", lambda *args, **kwargs: None)

    handler = ApiMessage(Flask("test_api_message_nonblocking"), threading.RLock())

    response = asyncio.run(
        handler.process(
            {
                "message": "Hello from the extension",
                "wait_for_response": False,
            },
            None,
        )
    )

    assert response["accepted"] is True
    assert response["status"] == "processing"
    assert response["context_id"] == "ctx-nonblocking"

    created_context = _FakeAgentContext.created[0]
    assert created_context.task.awaited is False
    assert created_context.log.entries[0]["type"] == "user"
