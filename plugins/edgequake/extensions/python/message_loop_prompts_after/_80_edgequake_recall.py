"""
EdgeQuake knowledge recall extension.

Fires before each LLM call. Queries EdgeQuake with the current user message
and injects relevant results into the agent's prompt context.

Guarded by:
- EdgeQuake must be configured (api_key set)
- auto_recall must be enabled in plugin settings
- 3-second timeout to avoid blocking the agent loop
- Only runs on the first iteration of each message loop
"""

import asyncio

from python.helpers.extension import Extension
from python.helpers.print_style import PrintStyle
from agent import LoopData


class EdgequakeRecall(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            # Only run on the first iteration to avoid repeated queries
            if loop_data.iteration != 0:
                return

            from plugins.edgequake.helpers.edgequake_client import (
                api_request,
                get_edgequake_settings,
            )

            settings = get_edgequake_settings()
            if not settings.get("auto_recall", False):
                return

            # Guard: need an API key configured
            if not settings.get("api_key", "").strip():
                return

            # Get user message text
            if not loop_data.user_message:
                return
            user_text = loop_data.user_message.output_text()
            if not user_text or len(user_text.strip()) < 3:
                return

            timeout = int(settings.get("recall_timeout", 3))
            if timeout < 1:
                timeout = 1

            log_item = self.agent.context.log.log(
                type="hint",
                heading="EdgeQuake: searching knowledge graph...",
            )

            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        api_request,
                        "POST",
                        "/api/v1/query",
                        {"query": user_text.strip(), "mode": "hybrid"},
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                log_item.update(heading="EdgeQuake: recall timed out")
                return

            if "error" in result:
                log_item.update(heading=f"EdgeQuake: recall failed — {result['error']}")
                return

            answer = result.get("response", result.get("answer", ""))
            if not answer or not answer.strip():
                log_item.update(heading="EdgeQuake: no relevant knowledge found")
                return

            # Inject into agent context as persistent extra so it survives
            # across tool-call iterations within this agent turn
            loop_data.extras_persistent["edgequake_knowledge"] = (
                "## EdgeQuake Knowledge Graph Context\n\n"
                "The following information was retrieved from the knowledge graph "
                "and may be relevant to the user's question:\n\n"
                f"{answer.strip()}"
            )

            log_item.update(
                heading="EdgeQuake: knowledge context injected",
                knowledge=answer.strip()[:500],
            )

        except Exception as e:
            # Non-blocking: log and continue
            PrintStyle.error(f"EdgeQuake recall error: {e}")
