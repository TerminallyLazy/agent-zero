import functools  
from agent import Agent  
from python.helpers.opik_llm_wrapper import OpikLLMWrapper  
  
def patch_agent_for_opik():  
    """Patch Agent class to include Opik tracking"""  
      
    # Store original methods  
    original_call_chat_model = Agent.call_chat_model  
    original_call_utility_model = Agent.call_utility_model  
      
    # Create wrapped methods  
    @functools.wraps(original_call_chat_model)  
    async def wrapped_call_chat_model(self, prompt, callback=None):  
        return await OpikLLMWrapper.track_chat_model_call(  
            self, original_call_chat_model, prompt, callback  
        )  
      
    @functools.wraps(original_call_utility_model)  
    async def wrapped_call_utility_model(self, system, message, callback=None, background=False):  
        return await OpikLLMWrapper.track_utility_model_call(  
            self, original_call_utility_model, system, message, callback, background  
        )  
      
    # Patch the Agent class  
    Agent.call_chat_model = wrapped_call_chat_model  
    Agent.call_utility_model = wrapped_call_utility_model