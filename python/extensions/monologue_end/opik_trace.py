from python.helpers.extension import Extension  
from python.helpers.opik_client import get_opik_tracker  
  
class OpikMonologueEnd(Extension):  
    async def execute(self, **kwargs):
        loop_data = kwargs.get('loop_data')
        if not loop_data:
            return
        tracker = get_opik_tracker()  
        if not tracker or not tracker.is_enabled():  
            return  
  
        trace_id = self.agent.get_data('opik_trace_id')  
        if not trace_id:  
            return  
  
        # End the agent conversation trace  
        tracker.end_trace(  
            trace_id=trace_id,  
            output_data={  
                'response': loop_data.last_response,  
                'iterations': loop_data.iteration + 1,  
                'agent': self.agent.agent_name  
            },  
            success=True  # We reached the end successfully  
        )  
          
        # Clean up  
        self.agent.set_data('opik_trace_id', None)
