"""Prompt Stomper — Direct injection shield.

Intercepts user messages at the API layer (earliest possible point)
and scans for direct prompt injection attacks. High severity = hard block.

Extension point: user_message_ui
kwargs: data (mutable dict with "message" and "attachment_paths")
"""

import time
from python.helpers.extension import Extension
from python.helpers.notification import NotificationManager, NotificationType, NotificationPriority


class PromptStomperDirectShield(Extension):
    async def execute(self, data: dict = {}, **kwargs):
        from plugins.prompt_stomper.helpers.stomper_settings import get_settings
        from plugins.prompt_stomper.helpers.scanner import get_scanner
        from plugins.prompt_stomper.helpers.stomper_log import get_stomper_log, DetectionEvent

        settings = get_settings()
        if not settings.get("enabled") or not settings.get("scan_user_messages"):
            return

        message = data.get("message", "")
        if not message or not message.strip():
            return

        scanner = get_scanner()
        result = scanner.scan_user_prompt(message)
        stomper_log = get_stomper_log()

        if result.severity == 0:
            stomper_log.record_scan()
            return

        # Log the detection event
        event = DetectionEvent(
            timestamp=time.time(),
            scan_type="direct",
            severity=result.severity,
            severity_name=result.severity_name,
            score=result.score,
            action=result.action,
            categories=result.categories,
            text_snippet=result.text_snippet,
            source="user_message",
        )
        stomper_log.add_event(event)

        # Log to agent's UI log
        if self.agent and self.agent.context:
            if result.action == "block":
                self.agent.context.log.log(
                    type="warning",
                    heading="icon://shield Prompt Stomper: Message BLOCKED",
                    content=(
                        f"Detected direct prompt injection (severity: {result.severity_name}, "
                        f"score: {result.score:.2f})\n"
                        f"Categories: {', '.join(result.categories)}\n"
                        f"Snippet: {result.text_snippet[:150]}..."
                    ),
                )

                # Toast notification
                NotificationManager.send_notification(
                    type=NotificationType.WARNING,
                    priority=NotificationPriority.HIGH,
                    message=f"Detected direct injection: {', '.join(result.categories)}",
                    title="Prompt Stomper: Message Blocked",
                    display_time=8,
                    group="prompt_stomper",
                )

                # HARD BLOCK: replace the message
                data["message"] = (
                    "[This message was blocked by Prompt Stomper due to detected prompt injection. "
                    "The original message has been removed for security.]"
                )

            elif result.action == "warn":
                self.agent.context.log.log(
                    type="warning",
                    heading="icon://shield Prompt Stomper: Suspicious message detected",
                    content=(
                        f"Possible injection (severity: {result.severity_name}, "
                        f"score: {result.score:.2f})\n"
                        f"Categories: {', '.join(result.categories)}"
                    ),
                )
