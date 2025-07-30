from agent import Agent, UserMessage
from python.helpers.tool import Tool, Response
import uuid


class CallSubordinate(Tool):

    async def execute(self, message="", reset="", profile="", **kwargs):
        """Create and execute subordinate agent with flow tracking."""
        
        # Create flow tracking for subordinate agent
        flow_id = str(uuid.uuid4())
        task_description = f"Subordinate agent task: {message[:100]}..."
        
        from python.api.agent_flow import flow_tracker
        flow_tracker.create_flow(
            flow_id=flow_id,
            parent_agent=getattr(self.agent, 'agent_name', 'main'),
            task_description=task_description
        )
        
        # create subordinate agent using the data object on this agent and set superior agent to his data object
        if (
            self.agent.get_data(Agent.DATA_NAME_SUBORDINATE) is None
            or str(reset).lower().strip() == "true"
        ):
            # create agent
            sub = Agent(self.agent.number + 1, self.agent.config, self.agent.context)
            # register superior/subordinate
            sub.set_data(Agent.DATA_NAME_SUPERIOR, self.agent)
            self.agent.set_data(Agent.DATA_NAME_SUBORDINATE, sub)
            # set default prompt profile to new agents
            sub.config.profile = ""

        # get subordinate agent
        subordinate: Agent = self.agent.get_data(Agent.DATA_NAME_SUBORDINATE)
        
        # add agent to flow tracking
        agent_id = f"subordinate_{subordinate.number}_{int(uuid.uuid4().hex[:8], 16)}"
        flow_tracker.add_agent_to_flow(flow_id, {
            "id": agent_id,
            "name": f"Subordinate Agent {subordinate.number}",
            "type": "subordinate",
            "role": profile or "subordinate",
            "status": "running",
            "message": message
        })
        
        # Register subordinate agent in the global agent registry
        from python.api.agents_list import register_subordinate_agent
        register_subordinate_agent(agent_id, {
            "name": f"@{profile or 'subordinate'}",
            "role": profile or "subordinate", 
            "status": "working",
            "parent_agent": getattr(self.agent, 'agent_name', 'main'),
            "profile": profile,
            "endpoint": f"local://{agent_id}",
            "task_count": 1
        })

        # add user message to subordinate agent
        subordinate.hist_add_user_message(UserMessage(message=message, attachments=[]))

        # set subordinate prompt profile if provided, if not, keep original
        agent_profile = kwargs.get("agent_profile") or profile
        if agent_profile:
            subordinate.config.profile = agent_profile

        try:
            # run subordinate monologue
            result = await subordinate.monologue()

            # Determine if task is complete
            is_complete = self._is_task_complete(result)

            if is_complete:
                # update agent status to completed
                flow_tracker.update_agent_status(flow_id, agent_id, "completed", 100)
                flow_tracker.complete_flow(flow_id, True)

                # Update agent registry status
                from python.api.agents_list import update_subordinate_agent
                update_subordinate_agent(agent_id, {
                    "status": "completed",
                    "task_count": 0
                })

                # Schedule cleanup after completion
                await self._schedule_cleanup(agent_id, subordinate, flow_id)
            else:
                # Task is ongoing, update progress
                flow_tracker.update_agent_status(flow_id, agent_id, "running", 75)

                from python.api.agents_list import update_subordinate_agent
                update_subordinate_agent(agent_id, {
                    "status": "working",
                    "task_count": 1
                })

        except Exception as e:
            # update agent status to failed
            flow_tracker.update_agent_status(flow_id, agent_id, "failed", 0)
            flow_tracker.complete_flow(flow_id, False)

            # Update agent registry status
            from python.api.agents_list import update_subordinate_agent
            update_subordinate_agent(agent_id, {
                "status": "error",
                "task_count": 0
            })

            # Schedule cleanup for failed agent
            await self._schedule_cleanup(agent_id, subordinate, flow_id)

            raise e

        # result
        return Response(message=result, break_loop=False)

    def _is_task_complete(self, result: str) -> bool:
        """Determine if the subordinate agent's task is complete."""
        completion_indicators = [
            "task completed", "finished", "done", "complete",
            "successfully", "final result", "conclusion",
            "task is finished", "work is done", "completed successfully"
        ]

        result_lower = result.lower()
        return any(indicator in result_lower for indicator in completion_indicators)

    async def _schedule_cleanup(self, agent_id: str, subordinate: Agent, flow_id: str):
        """Schedule cleanup of subordinate agent after task completion."""
        import asyncio

        async def cleanup_after_delay():
            # Wait 60 seconds before cleanup to allow for any final operations
            await asyncio.sleep(60)
            await self._cleanup_subordinate(agent_id, subordinate, flow_id)

        # Schedule cleanup task
        asyncio.create_task(cleanup_after_delay())

    async def _cleanup_subordinate(self, agent_id: str, subordinate: Agent, flow_id: str):
        """Clean up subordinate agent resources."""
        try:
            # Remove from agent registry
            from python.api.agents_list import remove_subordinate_agent
            remove_subordinate_agent(agent_id)

            # Update flow status to archived
            from python.api.agent_flow import flow_tracker
            flow_tracker.archive_flow(flow_id)

            # Clean up agent data
            if subordinate:
                subordinate.data.clear()

                # Remove subordinate reference from parent
                if self.agent.get_data(Agent.DATA_NAME_SUBORDINATE) == subordinate:
                    self.agent.set_data(Agent.DATA_NAME_SUBORDINATE, None)

            print(f"Cleaned up subordinate agent: {agent_id}")

        except Exception as e:
            print(f"Error during subordinate cleanup: {e}")


# Keep old class name for backward compatibility
class Delegation(CallSubordinate):
    pass

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://communication {self.agent.agent_name}: Calling Subordinate Agent",
            content="",
            kvps=self.args,
        )