from typing import Optional, Dict, Any
import uuid

try:
    import opik
    OPIK_AVAILABLE = True
except ImportError:
    OPIK_AVAILABLE = False
    opik = None
    print("Opik not installed. Install with: pip install opik")
  
from python.helpers.opik_config import OpikConfig  
from python.helpers.print_style import PrintStyle  
  
class OpikTracker:  
    def __init__(self, config: OpikConfig):  
        self.config = config  
        self.client: Optional[Any] = None
        self.active_traces: Dict[str, Any] = {}  
        self.session_id = str(uuid.uuid4())  
          
        if config.enabled and OPIK_AVAILABLE:
            try:
                # Set environment variables for Opik configuration
                import os

                if config.api_key:
                    os.environ["OPIK_API_KEY"] = config.api_key

                if config.endpoint:
                    os.environ["OPIK_URL_OVERRIDE"] = config.endpoint

                if config.project_name:
                    os.environ["OPIK_PROJECT_NAME"] = config.project_name

                if config.workspace:
                    os.environ["OPIK_WORKSPACE"] = config.workspace

                # Initialize Opik client using environment variables
                if opik is not None:
                    self.client = opik.Opik()
                else:
                    raise ImportError("Opik not available")

                PrintStyle(font_color="green").print(f"Opik initialized for project: {config.project_name} ({'self-hosted' if config.use_local else 'cloud'})")
            except Exception as e:
                PrintStyle(font_color="red").print(f"Failed to initialize Opik: {e}")
                self.config.enabled = False
  
    def is_enabled(self) -> bool:  
        return self.config.enabled and self.client is not None  
  
    def start_trace(self, name: str, input_data: Dict[str, Any],
                   metadata: Optional[Dict[str, Any]] = None,
                   trace_id: Optional[str] = None) -> Optional[str]:
        if not self.is_enabled():
            return None

        try:
            trace_id = trace_id or str(uuid.uuid4())

            # Create trace using Opik client
            if hasattr(self.client, 'trace'):
                trace = self.client.trace(  # type: ignore
                    name=name,
                    input=input_data,
                    metadata={
                        'session_id': self.session_id,
                        'tags': self.config.tags,
                        **(metadata or {}),
                        **self.config.additional_metadata
                    }
                )

                # Store trace reference for later use
                self.active_traces[trace_id] = trace
            return trace_id
        except Exception as e:
            PrintStyle(font_color="red").print(f"Error starting Opik trace: {e}")
            return None
  
    def end_trace(self, trace_id: str, output_data: Dict[str, Any],
                 success: bool = True, error: Optional[str] = None):
        if not self.is_enabled() or trace_id not in self.active_traces:
            return

        try:
            trace = self.active_traces[trace_id]

            # Update trace with output data
            trace.output = output_data
            if error:
                trace.metadata = {**(trace.metadata or {}), 'error': error, 'success': success}

            # The trace is automatically logged when it goes out of scope
            # or we can explicitly flush it
            del self.active_traces[trace_id]
        except Exception as e:
            PrintStyle(font_color="red").print(f"Error ending Opik trace: {e}")
  
    def log_llm_call(self, model_name: str, provider: str, input_text: str,
                    output_text: str, tokens_used: int, duration: float,
                    agent_name: str, metadata: Optional[Dict[str, Any]] = None):
        if not self.is_enabled():
            return

        try:
            # Create a trace for the LLM call
            if hasattr(self.client, 'trace'):
                trace = self.client.trace(  # type: ignore
                    name=f'LLM Call - {model_name}',
                    input={'prompt': input_text, 'model': model_name, 'provider': provider},
                    output={'response': output_text, 'tokens': tokens_used},
                    metadata={
                        'agent': agent_name,
                        'model': model_name,
                        'provider': provider,
                        'tokens': tokens_used,
                        'duration': duration,
                        'session_id': self.session_id,
                        'type': 'llm_call',
                        **(metadata or {})
                    },
                    tags=self.config.tags + ['llm', provider]
                )
                # Explicitly end the trace to ensure it's logged
                trace.end()
        except Exception as e:
            PrintStyle(font_color="red").print(f"Error logging LLM call to Opik: {e}")
  
    def log_tool_execution(self, tool_name: str, args: Dict[str, Any],
                          result: str, success: bool, duration: float,
                          agent_name: str, error: Optional[str] = None):
        if not self.is_enabled() or not self.config.trace_tools:
            return

        try:
            # Create a trace for the tool execution
            if hasattr(self.client, 'trace'):
                trace = self.client.trace(  # type: ignore
                    name=f'Tool - {tool_name}',
                    input={'tool': tool_name, 'args': args},
                    output={'result': result, 'success': success, 'error': error},
                    metadata={
                        'agent': agent_name,
                        'tool': tool_name,
                        'duration': duration,
                        'session_id': self.session_id,
                        'type': 'tool_execution'
                    },
                    tags=self.config.tags + ['tool', tool_name] + (['error'] if error else ['success'])
                )
                # Explicitly end the trace to ensure it's logged
                trace.end()
        except Exception as e:
            PrintStyle(font_color="red").print(f"Error logging tool execution to Opik: {e}")
  
    def log_agent_conversation(self, agent_name: str, user_message: str,
                             agent_response: str, success: bool,
                             metadata: Optional[Dict[str, Any]] = None):
        if not self.is_enabled():
            return

        try:
            # Create a trace for the agent conversation
            if hasattr(self.client, 'trace'):
                trace = self.client.trace(  # type: ignore
                    name=f'Agent Conversation - {agent_name}',
                    input={'user_message': user_message},
                    output={'agent_response': agent_response, 'success': success},
                    metadata={
                        'agent': agent_name,
                        'session_id': self.session_id,
                        'type': 'conversation',
                        **(metadata or {})
                    },
                    tags=self.config.tags + ['conversation', agent_name]
                )
                # Explicitly end the trace to ensure it's logged
                trace.end()
        except Exception as e:
            PrintStyle(font_color="red").print(f"Error logging conversation to Opik: {e}")

    def flush(self):
        """Flush any pending traces to Opik"""
        if self.is_enabled() and hasattr(self.client, 'flush'):
            try:
                self.client.flush()  # type: ignore
            except Exception as e:
                PrintStyle(font_color="red").print(f"Error flushing Opik client: {e}")

# Global tracker instance
_tracker: Optional[OpikTracker] = None
  
def get_opik_tracker() -> Optional[OpikTracker]:  
    global _tracker  
    if _tracker is None:  
        config = OpikConfig.from_env()  
        _tracker = OpikTracker(config)  
    return _tracker  
  
def initialize_opik(config: Optional[OpikConfig] = None) -> OpikTracker:  
    global _tracker  
    config = config or OpikConfig.from_env()  
    _tracker = OpikTracker(config)  
    return _tracker

