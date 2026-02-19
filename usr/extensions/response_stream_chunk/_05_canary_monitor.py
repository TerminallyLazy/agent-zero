"""Prompt Stomper — Canary token leak detection.

Monitors LLM output chunks for the canary token. If found, it means
the system prompt was leaked.

Extension point: response_stream_chunk
kwargs: stream_data (mutable dict with "chunk" and "full"), agent
"""

import time
from python.helpers.extension import Extension
from python.helpers.notification import NotificationManager, NotificationType, NotificationPriority


class CanaryMonitor(Extension):
    async def execute(self, **kwargs):
        from plugins.prompt_stomper.helpers.stomper_settings import get_settings

        settings = get_settings()
        if not settings.get("enabled") or not settings.get("canary_tokens"):
            return

        stream_data = kwargs.get("stream_data")
        if not stream_data:
            return

        full_text = stream_data.get("full", "")
        if not full_text:
            return

        # Import canary token from shared helper
        from plugins.prompt_stomper.helpers.canary import get_canary_token
        canary = get_canary_token()

        if canary in full_text:
            from plugins.prompt_stomper.helpers.stomper_log import get_stomper_log, DetectionEvent

            # Log the canary leak
            stomper_log = get_stomper_log()
            event = DetectionEvent(
                timestamp=time.time(),
                scan_type="canary",
                severity=3,
                severity_name="high",
                score=1.0,
                action="block",
                categories=["system_prompt_leak"],
                text_snippet=f"Canary token '{canary}' found in LLM output",
                source="canary_monitor",
            )
            stomper_log.add_event(event)

            # Redact the canary from the output
            stream_data["full"] = full_text.replace(canary, "[REDACTED]")
            chunk = stream_data.get("chunk", "")
            if canary in chunk:
                stream_data["chunk"] = chunk.replace(canary, "[REDACTED]")

            # Log warning
            agent = kwargs.get("agent") or self.agent
            if agent and agent.context:
                agent.context.log.log(
                    type="error",
                    heading="icon://shield Prompt Stomper: SYSTEM PROMPT LEAK DETECTED",
                    content=(
                        "The canary token was found in the LLM output, indicating the system "
                        "prompt was leaked. The token has been redacted from the response."
                    ),
                )

                NotificationManager.send_notification(
                    type=NotificationType.ERROR,
                    priority=NotificationPriority.HIGH,
                    message="The LLM output contained the canary token. System prompt may have been compromised.",
                    title="Prompt Stomper: System Prompt Leak!",
                    display_time=15,
                    group="prompt_stomper",
                )
