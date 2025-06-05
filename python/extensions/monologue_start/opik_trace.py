from python.helpers.extension import Extension  
from python.helpers.opik_client import get_opik_tracker  
  
class OpikMonologueStart(Extension):  
    async def execute(self, **kwargs):
        loop_data = kwargs.get('loop_data')
        if not loop_data:
            return
        tracker = get_opik_tracker()  
        if not tracker or not tracker.is_enabled():  
            return  
  
        # Start agent conversation trace  
        user_msg = ""  
        if loop_data.user_message and hasattr(loop_data.user_message, 'content'):  
            if isinstance(loop_data.user_message.content, dict):  
                user_msg = loop_data.user_message.content.get('message', '')  
            else:  
                user_msg = str(loop_data.user_message.content)  
  
        trace_id = tracker.start_trace(  
            name=f"Agent Monologue - {self.agent.agent_name}",  
            input_data={  
                'user_message': user_msg,  
                'agent': self.agent.agent_name,  
                'iteration': loop_data.iteration  
            },  
            metadata={  
                'agent_number': self.agent.number,  
                'context_id': self.agent.context.id  
            }  
        )  
          
        # Store trace ID for later use  
        self.agent.set_data('opik_trace_id', trace_id)
