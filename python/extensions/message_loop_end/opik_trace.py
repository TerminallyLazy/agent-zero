from python.helpers.extension import Extension  
from python.helpers.opik_client import get_opik_tracker  
  
class OpikMessageLoopEnd(Extension):  
    async def execute(self, **kwargs):
        loop_data = kwargs.get('loop_data')
        if not loop_data:
            return
        tracker = get_opik_tracker()  
        if not tracker or not tracker.is_enabled():  
            return  
  
        trace_id = self.agent.get_data(f'opik_loop_trace_{loop_data.iteration}')  
        if not trace_id:  
            return  
  
        # End message loop trace  
        tracker.end_trace(  
            trace_id=trace_id,  
            output_data={  
                'iteration': loop_data.iteration,  
                'response': loop_data.last_response,  
                'agent': self.agent.agent_name  
            },  
            success=True  
        )  
          
        # Clean up  
        self.agent.set_data(f'opik_loop_trace_{loop_data.iteration}', None)
