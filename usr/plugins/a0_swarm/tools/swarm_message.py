from __future__ import annotations

from agent import AgentContext, UserMessage
from helpers.tool import Tool, Response
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmMessage, SwarmAgentStatus, utc_iso_now,
)


class SwarmMessageTool(Tool):
    async def execute(
        self,
        recipient: str = "orchestrator",
        content: str = "",
        is_blocker: bool = False,
        **kwargs,
    ):
        reg = SwarmRegistry.get()
        sender_entry = reg.get_agent_by_context(self.agent.context.id)
        sender_name = sender_entry.agent_name if sender_entry else self.agent.agent_name

        reg.add_message(SwarmMessage(
            sender=sender_name, recipient=recipient,
            content=content, timestamp=utc_iso_now(),
        ))

        if is_blocker and sender_entry:
            reg.update_status(sender_name, SwarmAgentStatus.BLOCKED, blocker=content)

        if recipient != "orchestrator":
            target = reg.get_agent(recipient)
            if target:
                ctx = AgentContext.get(target.context_id)
                if ctx:
                    ctx.communicate(UserMessage(
                        message=f"[Message from {sender_name}]: {content}"
                    ))

        return Response(message=f"Message sent to {recipient}.", break_loop=False)

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://message {self.agent.agent_name}: Swarm Message",
            content=self.args.get("content", ""),
            kvps=self.args,
        )
