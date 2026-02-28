"""Auto-context injection via Context Engine.

Periodically searches the codebase using the conversation history and
injects relevant code snippets into the agent's prompt extras. Runs as
an async task so it does not block the message loop.
"""

import asyncio
import importlib.util
import os

from python.helpers.extension import Extension
from python.helpers import errors, log, plugins
from agent import LoopData

DATA_NAME_TASK = "_ce_auto_context_task"
SEARCH_TIMEOUT = 15


def _load_client():
    """Import ContextEngineClient via file path (bypasses hyphen in dir name)."""
    client_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "helpers", "client.py"
    )
    client_path = os.path.normpath(client_path)
    spec = importlib.util.spec_from_file_location("context_engine_client", client_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ContextEngineClient


class AutoContext(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        config = plugins.get_plugin_config("context-engine", self.agent)
        if not config:
            return

        if not config.get("auto_context_enabled", False):
            return

        interval = config.get("auto_context_interval", 3)

        # Run on first iteration (0) and then every `interval` iterations
        if loop_data.iteration != 0 and loop_data.iteration % interval != 0:
            return

        log_item = self.agent.context.log.log(
            type="util",
            heading="Searching codebase for context...",
        )

        task = asyncio.create_task(
            asyncio.wait_for(
                self._search(config, loop_data, log_item),
                timeout=SEARCH_TIMEOUT,
            )
        )

        # Store task so the wait extension can await it before LLM call
        self.agent.set_data(DATA_NAME_TASK, task)

    async def _search(
        self,
        config: dict,
        loop_data: LoopData,
        log_item: log.LogItem,
    ):
        try:
            ContextEngineClient = _load_client()
            client = ContextEngineClient(config)

            # Build query from recent history + current user message
            history_len = config.get("auto_context_history_len", 10000)
            history_text = self.agent.history.output_text()[-history_len:]
            user_msg = (
                loop_data.user_message.output_text()
                if loop_data.user_message
                else ""
            )
            query = (user_msg + "\n" + history_text).strip()
            if not query or len(query) <= 3:
                log_item.update(heading="No context query to search")
                return

            max_results = config.get("auto_context_max_results", 5)
            result = await client.search(query=query, limit=max_results)

            if not result.get("ok", True) or "error" in result:
                log_item.update(
                    heading="Context Engine unavailable",
                    content=result.get("error", "Unknown error"),
                )
                return

            snippets = result.get("results", [])
            if not snippets:
                log_item.update(heading="No relevant code context found")
                return

            # Format snippets for prompt injection
            lines = []
            for item in snippets:
                path = item.get("path", "?")
                start = item.get("start_line", "")
                symbol = item.get("symbol", "")
                snippet = item.get("snippet", "")
                header = path
                if start:
                    header += f":{start}"
                if symbol:
                    header += f" ({symbol})"
                lines.append(f"### {header}")
                if snippet:
                    lines.append(f"```\n{snippet}\n```")

            context_text = "\n\n".join(lines)

            log_item.update(
                heading=f"{len(snippets)} code context snippets injected",
            )

            # Inject into persistent extras so they survive across iterations
            loop_data.extras_persistent["ce_auto_context"] = (
                self.agent.read_prompt(
                    "agent.extras.ce_auto_context.md",
                    context=context_text,
                )
            )

        except asyncio.TimeoutError:
            log_item.update(heading="Context Engine search timed out")
        except Exception as exc:
            err = errors.format_error(exc)
            self.agent.context.log.log(
                type="warning",
                heading="Auto-context extension error:",
                content=err,
            )
