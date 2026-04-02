from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import models
from aiohttp.client_exceptions import ServerDisconnectedError
from litellm.exceptions import MidStreamFallbackError


class _FakeAsyncStream:
    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        if isinstance(item, Exception):
            raise item
        return item


def _run(awaitable):
    return asyncio.run(awaitable)


def test_unified_call_retries_reasoning_only_midstream_disconnect(monkeypatch):
    model = models.LiteLLMChatWrapper(
        model="gemini-test",
        provider="gemini",
        model_config=models.ModelConfig(
            type=models.ModelType.CHAT,
            provider="google",
            name="gemini-test",
        ),
    )

    calls = {"count": 0}

    async def _fake_rate_limiter(*args, **kwargs):
        return None

    async def _fake_acompletion(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeAsyncStream(
                [
                    {"choices": [{"delta": {"reasoning_content": "thinking..."}}]},
                    MidStreamFallbackError(
                        message="Server disconnected",
                        model="gemini-test",
                        llm_provider="vertex_ai_beta",
                        generated_content="thinking...",
                        is_pre_first_chunk=False,
                    ),
                ]
            )
        return _FakeAsyncStream(
            [
                {"choices": [{"delta": {"content": "{\"tool_name\":\"response\"}"}}]},
            ]
        )

    monkeypatch.setattr(models, "apply_rate_limiter", _fake_rate_limiter)
    monkeypatch.setattr(models, "acompletion", _fake_acompletion)

    async def _noop(*args, **kwargs):
        return None

    response, reasoning = _run(
        model.unified_call(
            user_message="Hello",
            reasoning_callback=_noop,
            a0_retry_attempts=1,
            a0_retry_delay_seconds=0,
        )
    )

    assert calls["count"] == 2
    assert response == '{"tool_name":"response"}'
    assert reasoning == ""


def test_transient_error_detection_treats_server_disconnect_as_retryable():
    assert models._is_transient_litellm_error(ServerDisconnectedError()) is True
