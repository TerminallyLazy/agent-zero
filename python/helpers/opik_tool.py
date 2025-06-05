import time  
from typing import Dict, Any  
from python.helpers.tool import Tool, Response  
from python.helpers.opik_client import get_opik_tracker  
  
class OpikTool(Tool):  
    """Enhanced Tool class with Opik tracing"""  
      
    def __init__(self, agent, name: str, args: dict[str,str], message: str, **kwargs):  
        super().__init__(agent=agent, name=name, method=None, args=args, message=message, **kwargs)  
        self.start_time = None  
        self.tracker = get_opik_tracker()  
  
    async def before_execution(self, **kwargs):  
        self.start_time = time.time()  
        await super().before_execution(**kwargs)  
  
    async def after_execution(self, response: Response, **kwargs):  
        duration = time.time() - self.start_time if self.start_time else 0  
          
        # Log to Opik  
        if self.tracker and self.tracker.is_enabled():  
            self.tracker.log_tool_execution(  
                tool_name=self.name,  
                args=self.args,  
                result=response.message,  
                success=not hasattr(response, 'error'),  
                duration=duration,  
                agent_name=self.agent.agent_name,  
                error=getattr(response, 'error', None)  
            )  
          
        await super().after_execution(response, **kwargs)
