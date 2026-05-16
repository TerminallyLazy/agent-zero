from __future__ import annotations

from helpers.tool import Tool, Response
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgentStatus,
)
from usr.plugins.a0_swarm.helpers import delivery


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

        if not sender_entry:
            return Response(message="swarm_message failed: sender is not registered in a swarm run.", break_loop=False)

        try:
            msg = reg.create_message(
                sender_entry.run_id,
                sender_name,
                recipient,
                content,
            )
        except ValueError as exc:
            return Response(message=f"swarm_message failed: {exc}", break_loop=False)

        if is_blocker:
            reg.update_status(sender_name, SwarmAgentStatus.BLOCKED, blocker=content)

        result = await delivery.deliver_message(msg.message_id)
        if result.ok:
            state_text = result.state
        else:
            state_text = f"{result.state}: {result.reason}"

        return Response(
            message=f"Message {msg.message_id} accepted for {recipient}; delivery_state={state_text}.",
            break_loop=False,
        )

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://message {self.agent.agent_name}: Swarm Message",
            content=self.args.get("content", ""),
            kvps=self.args,
        )
