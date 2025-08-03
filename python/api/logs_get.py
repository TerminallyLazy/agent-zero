from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from agent import AgentContext


class LogsGet(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        try:
            context_id = input.get('context_id', '')
            after_log_index = input.get('after_log_index', 0)
            limit = input.get('limit', 50)
            
            if not context_id:
                return {
                    "success": False,
                    "message": "Context ID is required",
                    "logs": []
                }
            
            # Get the context
            context = AgentContext.get(context_id)
            if not context:
                return {
                    "success": False,
                    "message": f"Context {context_id} not found",
                    "logs": []
                }
            
            # Get logs after specified index
            all_logs = context.log.logs
            new_logs = [log for log in all_logs if (log.id or 0) > after_log_index]
            
            # Limit results
            limited_logs = new_logs[:limit]
            
            # Convert to serializable format
            serialized_logs = []
            for log_item in limited_logs:
                # Handle timestamp safely - check various possible attributes
                timestamp = None
                if hasattr(log_item, 'timestamp') and log_item.timestamp:
                    timestamp = log_item.timestamp.isoformat()
                elif hasattr(log_item, 'created_at') and log_item.created_at:
                    timestamp = log_item.created_at.isoformat()
                elif hasattr(log_item, 'time') and log_item.time:
                    timestamp = log_item.time.isoformat()
                
                serialized_logs.append({
                    'id': log_item.id,
                    'type': log_item.type.value if hasattr(log_item.type, 'value') else str(log_item.type),
                    'heading': log_item.heading,
                    'content': log_item.content,
                    'timestamp': timestamp,
                    'kvps': log_item.kvps if hasattr(log_item, 'kvps') else {}
                })
            
            return {
                "success": True,
                "logs": serialized_logs,
                "is_running": context.task and context.task.is_alive() if context.task else False
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to get logs: {str(e)}",
                "logs": []
            }