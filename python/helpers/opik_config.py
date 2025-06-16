import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class OpikConfig:
    enabled: bool = True  
    api_key: Optional[str] = None  
    endpoint: Optional[str] = None  # For self-hosted, this will be your local URL  
    project_name: str = "agent-zero"  
    workspace: Optional[str] = None  
    use_local: bool = True  # New flag for self-hosted  
    tags: list[str] = field(default_factory=lambda: ["agent-zero"])  
    additional_metadata: Dict[str, Any] = field(default_factory=dict)  
    trace_tools: bool = True   
    trace_llm_calls: bool = True  
    trace_subordinates: bool = True  
    trace_errors: bool = True  
      
    @classmethod  
    def from_env(cls) -> 'OpikConfig':  
        return cls(  
            enabled=os.getenv('OPIK_ENABLED', 'true').lower() == 'true',  
            api_key=os.getenv('OPIK_API_KEY'),  # May not be needed for self-hosted  
            endpoint=os.getenv('OPIK_ENDPOINT', 'http://localhost:5173'),  # Default self-hosted URL  
            project_name=os.getenv('OPIK_PROJECT_NAME', 'agent-zero'),  
            workspace=os.getenv('OPIK_WORKSPACE'),  
            use_local=os.getenv('OPIK_USE_LOCAL', 'true').lower() == 'true',  
            tags=os.getenv('OPIK_TAGS', 'agent-zero').split(','),  
            trace_tools=os.getenv('OPIK_TRACE_TOOLS', 'true').lower() == 'true',  
            trace_llm_calls=os.getenv('OPIK_TRACE_LLM', 'true').lower() == 'true',  
            trace_subordinates=os.getenv('OPIK_TRACE_SUBORDINATES', 'true').lower() == 'true',  
            trace_errors=os.getenv('OPIK_TRACE_ERRORS', 'true').lower() == 'true',  
        )