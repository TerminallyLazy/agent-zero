

import time  
from python.tools.call_subordinate import Delegation as CallSubordinate
from python.helpers.tool import Response  
from python.helpers.opik_client import get_opik_tracker  
  
class OpikCallSubordinate(CallSubordinate):  
    """Enhanced CallSubordinate with Opik tracing"""  
      
    async def execute(self, message="", reset="", **kwargs) -> Response:  
        tracker = get_opik_tracker()  
        start_time = time.time()  
          
        # Start subordinate trace  
        trace_id = None  
        if tracker and tracker.is_enabled() and tracker.config.trace_subordinates:  
            trace_id = tracker.start_trace(  
                name=f"Subordinate Call - {self.agent.agent_name} -> Agent {kwargs.get('number', 'Unknown')}",  
                input_data={  
                    'parent_agent': self.agent.agent_name,  
                    'subordinate_number': kwargs.get('number'),  
                    'message': kwargs.get('message', ''),  
                    'args': self.args  
                },  
                metadata={  
                    'type': 'subordinate_call',  
                    'parent_agent_number': self.agent.number  
                }  
            )  
          
        try:  
            # Execute original subordinate call  
            response = await super().execute(**kwargs)  
            duration = time.time() - start_time  
              
            # End trace with success  
            if trace_id and tracker:  
                tracker.end_trace(  
                    trace_id=trace_id,  
                    output_data={  
                        'response': response.message,  
                        'success': True,  
                        'duration': duration  
                    },  
                    success=True  
                )  
              
            return response  
              
        except Exception as e:  
            duration = time.time() - start_time  
              
            # End trace with error  
            if trace_id and tracker:  
                tracker.end_trace(  
                    trace_id=trace_id,  
                    output_data={  
                        'error': str(e),  
                        'success': False,  
                        'duration': duration  
                    },  
                    success=False,  
                    error=str(e)  
                )  
              
            raise
