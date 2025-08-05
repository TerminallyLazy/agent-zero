from helpers.tool import Tool, Response
from agent import Agent, UserMessage


class CallSubordinate(Tool):
    """
    Tool for delegating tasks to a subordinate agent.
    """
    async def execute(self, message="", reset="", **kwargs):
        # Create subordinate agent using the data object on this agent
        # and set superior agent to its data object
        if (
            self.agent.get_data(Agent.DATA_NAME_SUBORDINATE) is None
            or str(reset).lower().strip() == "true"
        ):
            # Create agent
            sub = Agent(self.agent.number + 1, self.agent.config, self.agent.context)
            # Register superior/subordinate relationship
            sub.set_data(Agent.DATA_NAME_SUPERIOR, self.agent)
            self.agent.set_data(Agent.DATA_NAME_SUBORDINATE, sub)
            # Set default prompt profile to new agent
            sub.config.profile = ""
        
        # Add user message to subordinate agent
        subordinate: Agent = self.agent.get_data(Agent.DATA_NAME_SUBORDINATE)
        subordinate.hist_add_user_message(UserMessage(message=message))
        
        # Set subordinate prompt profile if provided, if not, keep original
        agent_profile = kwargs.get("agent_profile")
        if agent_profile:
            subordinate.config.profile = agent_profile
        
        # Run subordinate monologue
        result = await subordinate.monologue()
        
        # Return result
        return Response(message=result, break_loop=False)