from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from agent import AgentContext
from initialize import initialize_agent


class ContextNew(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        try:
            # Get context name and system prompt from input
            context_name = input.get('name', 'Clinical Inbox Agent')
            system_prompt = input.get('system_prompt', '')
            
            # Create new Agent Zero context
            config = initialize_agent()
            context = AgentContext(config=config, name=context_name)
            
            # If system prompt provided, add it
            if system_prompt:
                from agent import UserMessage
                user_msg = UserMessage(message="", system_message=[system_prompt])
                context.agent0.hist_add_user_message(user_msg)
            
            return {
                "success": True,
                "context_id": context.id,
                "name": context.name,
                "message": "Agent context created successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to create context: {str(e)}"
            }