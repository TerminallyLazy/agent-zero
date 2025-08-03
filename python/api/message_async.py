from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from agent import AgentContext, UserMessage
from python.helpers.print_style import PrintStyle


class MessageAsync(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        try:
            context_id = input.get('context_id', '')
            message = input.get('message', '')
            attachments = input.get('attachments', [])
            
            if not context_id:
                return {
                    "success": False,
                    "message": "Context ID is required"
                }
            
            if not message:
                return {
                    "success": False, 
                    "message": "Message is required"
                }
            
            # Get the context
            context = AgentContext.get(context_id)
            if not context:
                return {
                    "success": False,
                    "message": f"Context {context_id} not found"
                }
            
            # Create user message
            user_msg = UserMessage(
                message=message,
                attachments=attachments
            )
            
            # Send message to context (async)
            task = context.communicate(user_msg)
            
            PrintStyle(font_color="blue").print(f"Message sent to context {context_id}: {message[:50]}...")
            
            return {
                "success": True,
                "context_id": context_id,
                "message": "Message sent successfully",
                "task_id": context.id if task else None
            }
            
        except Exception as e:
            PrintStyle(font_color="red").print(f"Message async failed: {e}")
            return {
                "success": False,
                "message": f"Failed to send message: {str(e)}"
            }