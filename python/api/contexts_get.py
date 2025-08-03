from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from agent import AgentContext


class ContextsGet(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        try:
            # Get all Agent Zero contexts
            contexts = AgentContext.get_all()
            
            # Convert contexts to serializable format
            context_list = []
            for context in contexts:
                context_data = {
                    'id': context.id,
                    'name': getattr(context, 'name', f'Context {context.id}'),
                    'created_at': context.created.isoformat() if hasattr(context, 'created') and context.created else None,
                    'is_active': bool(context.task and context.task.is_alive() if hasattr(context, 'task') and context.task else False),
                    'message_count': len(context.log.logs) if hasattr(context, 'log') and context.log else 0
                }
                context_list.append(context_data)
            
            return {
                "success": True,
                "contexts": context_list,
                "total": len(context_list)
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to get contexts: {str(e)}",
                "contexts": []
            }