from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from usr.plugins.chrome_extension.extensions.python.system_prompt._20_chrome_context import ChromeContextPrompt
from usr.plugins.chrome_extension.helpers.constants import CTX_BROWSER_SESSION_ID, CTX_SOURCE, SOURCE_NAME


class _DummyContext:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}


class _DummyAgent:
    def __init__(self) -> None:
        self.context = _DummyContext()

    def read_prompt(self, file: str, **kwargs) -> str:
        return f"{file}:{kwargs['browser_session_id']}"


def test_chrome_prompt_is_injected_for_bound_browser_session(monkeypatch) -> None:
    agent = _DummyAgent()
    agent.context.data[CTX_SOURCE] = SOURCE_NAME
    agent.context.data[CTX_BROWSER_SESSION_ID] = "browser-session-1"
    prompts: list[str] = []

    monkeypatch.setattr(
        "usr.plugins.chrome_extension.extensions.python.system_prompt._20_chrome_context.plugins.get_plugin_config",
        lambda *args, **kwargs: {"prompt_guidance": "Prefer the connected Chrome session."},
    )

    extension = ChromeContextPrompt(agent)
    asyncio.run(extension.execute(system_prompt=prompts))

    assert prompts == [
        "fw.chrome.system_context.md:browser-session-1\n- Prefer the connected Chrome session."
    ]


def test_chrome_prompt_skips_non_extension_context() -> None:
    agent = _DummyAgent()
    prompts: list[str] = []

    extension = ChromeContextPrompt(agent)
    asyncio.run(extension.execute(system_prompt=prompts))

    assert prompts == []
