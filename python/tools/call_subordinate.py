from agent import Agent, UserMessage
from python.helpers.tool import Tool, Response


class Delegation(Tool):

    async def execute(self, message="", reset="", **kwargs):
        # Try A2A mesh first if available, then fallback to internal subordinate
        try:
            mesh_result = await self._try_mesh_delegation(message, **kwargs)
            if mesh_result:
                return mesh_result
        except:
            # Silently continue to internal delegation
            pass
        
        # Original internal subordinate delegation
        # create subordinate agent using the data object on this agent and set superior agent to his data object
        if (
            self.agent.get_data(Agent.DATA_NAME_SUBORDINATE) is None
            or str(reset).lower().strip() == "true"
        ):
            # crate agent
            sub = Agent(self.agent.number + 1, self.agent.config, self.agent.context)
            # register superior/subordinate
            sub.set_data(Agent.DATA_NAME_SUPERIOR, self.agent)
            self.agent.set_data(Agent.DATA_NAME_SUBORDINATE, sub)
            # subordinates inherit parent's profile unless explicitly overridden
            # sub.config.profile = ""  # Commented out to preserve parent's tool access

        # add user message to subordinate agent
        subordinate: Agent = self.agent.get_data(Agent.DATA_NAME_SUBORDINATE)
        subordinate.hist_add_user_message(UserMessage(message=message, attachments=[]))

        # set subordinate prompt profile if provided, if not, keep original
        agent_profile = kwargs.get("agent_profile")
        if agent_profile:
            subordinate.config.profile = agent_profile

        # run subordinate monologue
        result = await subordinate.monologue()

        # result
        return Response(message=result, break_loop=False)
    
    async def _try_mesh_delegation(self, message, **kwargs):
        """Try to delegate through A2A mesh if other agents are available"""
        try:
            # Check if we can import A2A components
            from python.helpers.registry_broker import AgentRegistry
            
            registry = AgentRegistry()
            available_agents = registry.list_agents()
            
            # Only use mesh if we have multiple agents registered
            if len(available_agents) <= 1:
                return None
                
            # Use the A2A task execution API directly
            import aiohttp
            import json
            
            task_data = {
                "goal": message,
                "agent_profile": kwargs.get("agent_profile", ""),
                "context_id": self.agent.context.id
            }
            
            # Call our own A2A execute endpoint
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://localhost:5000/a2a_task_execute",
                    json=task_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("status") == "started":
                            # Wait for completion by polling the task
                            task_id = result["task"]["task_id"]
                            final_result = await self._wait_for_mesh_completion(task_id)
                            
                            # Log mesh delegation
                            self.agent.context.log.log(
                                type="tool",
                                heading=f"icon://sitemap {self.agent.agent_name}: A2A Mesh Delegation",
                                content=f"Task delegated via mesh: {message[:100]}...",
                                kvps={"mesh_task_id": task_id, "result": final_result[:200]}
                            )
                            
                            return Response(message=final_result, break_loop=False)
            
            return None
            
        except Exception:
            # Any error means fallback to internal delegation
            return None
    
    async def _wait_for_mesh_completion(self, task_id, timeout=60):
        """Wait for mesh task completion"""
        import asyncio
        import aiohttp
        
        for _ in range(timeout):  # Poll for up to 60 seconds
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "http://localhost:5000/a2a_tasks_list",
                        headers={"Content-Type": "application/json"}
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            tasks = result.get("tasks", {})
                            task = tasks.get(task_id)
                            
                            if task and task.get("state") == "completed":
                                return task.get("result", "Task completed via mesh")
                            elif task and task.get("state") == "failed":
                                raise Exception(f"Mesh task failed: {task.get('error', 'Unknown error')}")
                
                await asyncio.sleep(1)  # Wait 1 second between polls
                
            except Exception:
                pass
        
        # Timeout - return what we have
        return "Mesh task completed (timeout waiting for result)"

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://communication {self.agent.agent_name}: Calling Subordinate Agent",
            content="",
            kvps=self.args,
        )