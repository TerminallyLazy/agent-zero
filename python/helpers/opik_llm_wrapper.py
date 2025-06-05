import time  
import asyncio  
from typing import Callable, Awaitable, Optional  
from python.helpers.opik_client import get_opik_tracker  
from agent import Agent  
  
class OpikLLMWrapper:  
    """Wrapper to track LLM calls with Opik"""  
      
    @staticmethod  
    async def track_chat_model_call(  
        agent: Agent,  
        original_method: Callable,  
        prompt,  
        callback: Optional[Callable[[str, str], Awaitable[None]]] = None  
    ):  
        tracker = get_opik_tracker()  
        start_time = time.time()  
          
        # Get model info  
        model_config = agent.config.chat_model  
        model_name = model_config.name  
        provider = model_config.provider.value  
          
        # Get input text  
        input_text = prompt.format() if hasattr(prompt, 'format') else str(prompt)  
          
        try:  
            # Call original method  
            response = await original_method(prompt, callback)  
            duration = time.time() - start_time  
              
            # Log to Opik  
            if tracker and tracker.is_enabled() and tracker.config.trace_llm_calls:  
                # Approximate token count (you might want to use tiktoken for accuracy)  
                from python.helpers import tokens  
                token_count = tokens.approximate_tokens(input_text + response)  
                  
                tracker.log_llm_call(  
                    model_name=model_name,  
                    provider=provider,  
                    input_text=input_text,  
                    output_text=response,  
                    tokens_used=token_count,  
                    duration=duration,  
                    agent_name=agent.agent_name  
                )  
              
            return response  
              
        except Exception as e:  
            duration = time.time() - start_time  
              
            # Log error to Opik  
            if tracker and tracker.is_enabled():  
                tracker.log_llm_call(  
                    model_name=model_name,  
                    provider=provider,  
                    input_text=input_text,  
                    output_text=f"ERROR: {str(e)}",  
                    tokens_used=0,  
                    duration=duration,  
                    agent_name=agent.agent_name,  
                    metadata={'error': str(e)}  
                )  
              
            raise  
  
    @staticmethod  
    async def track_utility_model_call(  
        agent: Agent,  
        original_method: Callable,  
        system: str,  
        message: str,  
        callback: Optional[Callable[[str], Awaitable[None]]] = None,  
        background: bool = False  
    ):  
        tracker = get_opik_tracker()  
        start_time = time.time()  
          
        # Get model info  
        model_config = agent.config.utility_model  
        model_name = model_config.name  
        provider = model_config.provider.value  
          
        input_text = f"System: {system}\nMessage: {message}"  
          
        try:  
            # Call original method  
            response = await original_method(system, message, callback, background)  
            duration = time.time() - start_time  
              
            # Log to Opik  
            if tracker and tracker.is_enabled() and tracker.config.trace_llm_calls:  
                from python.helpers import tokens  
                token_count = tokens.approximate_tokens(input_text + response)  
                  
                tracker.log_llm_call(  
                    model_name=model_name,  
                    provider=provider,  
                    input_text=input_text,  
                    output_text=response,  
                    tokens_used=token_count,  
                    duration=duration,  
                    agent_name=agent.agent_name,  
                    metadata={'type': 'utility', 'background': background}  
                )  
              
            return response  
              
        except Exception as e:  
            duration = time.time() - start_time  
              
            # Log error to Opik  
            if tracker and tracker.is_enabled():  
                tracker.log_llm_call(  
                    model_name=model_name,  
                    provider=provider,  
                    input_text=input_text,  
                    output_text=f"ERROR: {str(e)}",  
                    tokens_used=0,  
                    duration=duration,  
                    agent_name=agent.agent_name,  
                    metadata={'error': str(e), 'type': 'utility'}  
                )  
              
            raise