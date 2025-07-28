import asyncio
import json
import time
from typing import Dict, Any, Optional, List, Callable, Awaitable, Tuple
from dataclasses import dataclass

from python.helpers.tool import Tool, Response
from python.helpers.concurrency_limiter import ConcurrencyLimiter
from python.helpers.print_style import PrintStyle
from python.helpers.tokens import approximate_tokens
from python.tools.agent_bridge import AgentBridge, discover_agent
from models import get_chat_model, ModelConfig, ModelType
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage


@dataclass
class LLMCallResult:
    """Result from an LLM call operation."""
    response: str
    reasoning: str = ""
    model_used: str = ""
    provider: str = ""
    tokens_used: int = 0
    duration: float = 0.0
    source: str = "local"  # "local" or "remote"
    remote_agent: Optional[str] = None


class LLMBridge(Tool):
    """
    Bridge tool for making LLM calls with concurrency control and remote agent delegation.
    
    This tool wraps Agent Zero's existing LiteLLM functionality and extends it with:
    - Concurrency limiting to prevent rate limit violations
    - Remote agent delegation for distributed LLM calls
    - Unified interface for both local and remote LLM access
    - Session management and caching
    """

    async def execute(self, **kwargs) -> Response:
        """
        Execute an LLM call with optional remote agent delegation.
        
        Args (via self.args):
            prompt: The user prompt/message for the LLM
            system_message: Optional system message (default: "")
            model: Model name to use (optional, uses agent's default)
            provider: Provider name (optional, uses agent's default)
            remote_agent: Remote agent endpoint for delegation (optional)
            max_tokens: Maximum tokens to generate (optional)
            temperature: Temperature for generation (optional, default: 0.7)
            stream: Whether to stream the response (optional, default: True)
            timeout: Request timeout in seconds (default: 60)
            
        Returns:
            Response containing the LLM result
        """
        try:
            prompt = self.args.get("prompt", "").strip()
            if not prompt:
                return Response(
                    message="Error: prompt parameter is required",
                    break_loop=False
                )
            
            system_message = self.args.get("system_message", "")
            model = self.args.get("model", "")
            provider = self.args.get("provider", "")
            remote_agent = self.args.get("remote_agent", "").strip()
            timeout = float(self.args.get("timeout", 60))
            
            # Parse additional parameters
            max_tokens = self._parse_int(self.args.get("max_tokens"))
            temperature = self._parse_float(self.args.get("temperature", "0.7"))
            stream = self._parse_bool(self.args.get("stream", "true"))
            
            PrintStyle(font_color="#2E86AB", bold=True).print(
                f"LLM Bridge: Calling {'remote agent' if remote_agent else 'local LLM'}"
            )
            
            start_time = time.time()
            
            if remote_agent:
                result = await self._call_remote_llm(
                    remote_agent, prompt, system_message, timeout,
                    model, max_tokens, temperature
                )
            else:
                result = await self._call_local_llm(
                    prompt, system_message, model, provider,
                    max_tokens, temperature, stream
                )
            
            result.duration = time.time() - start_time
            
            return self._format_response(result)
            
        except Exception as e:
            error_msg = f"LLM bridge error: {str(e)}"
            PrintStyle(font_color="red", bold=True).print(error_msg)
            return Response(message=error_msg, break_loop=False)

    async def _call_local_llm(
        self,
        prompt: str,
        system_message: str,
        model: str,
        provider: str,
        max_tokens: Optional[int],
        temperature: float,
        stream: bool
    ) -> LLMCallResult:
        """Call local LLM using Agent Zero's existing infrastructure."""
        
        # Use agent's configured model if not specified
        if not model or not provider:
            chat_model = self.agent.get_chat_model()
            model_name = chat_model.model_name
            provider_name = chat_model.provider
        else:
            # Create model instance with specified parameters
            model_config = ModelConfig(
                type=ModelType.CHAT,
                provider=provider,
                name=model
            )
            chat_model = get_chat_model(provider, model, **model_config.build_kwargs())
            model_name = model
            provider_name = provider
        
        # Build kwargs for the call
        call_kwargs = {}
        if max_tokens:
            call_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        if not stream:
            call_kwargs["stream"] = False
        
        # Prepare messages
        messages: List[BaseMessage] = []
        if system_message:
            messages.append(SystemMessage(content=system_message))
        messages.append(HumanMessage(content=prompt))
        
        # Apply concurrency limiting based on provider
        concurrency_key = f"llm_bridge_{provider_name}"
        max_concurrent = self._get_provider_concurrency(provider_name)
        
        response_chunks = []
        reasoning_chunks = []
        tokens_used = 0
        
        async def response_callback(chunk: str, full: str):
            response_chunks.append(chunk)
            if stream:
                PrintStyle(font_color="#85C1E9").stream(chunk)
        
        async def reasoning_callback(chunk: str, full: str):
            reasoning_chunks.append(chunk)
        
        async def tokens_callback(delta: str, tokens: int):
            nonlocal tokens_used
            tokens_used += tokens
        
        async with ConcurrencyLimiter.guard(concurrency_key, max_concurrent):
            response, reasoning = await chat_model.unified_call(
                messages=messages,
                response_callback=response_callback if stream else None,
                reasoning_callback=reasoning_callback,
                tokens_callback=tokens_callback,
                **call_kwargs
            )
        
        if stream:
            PrintStyle().print()  # New line after streaming
        
        return LLMCallResult(
            response=response,
            reasoning=reasoning,
            model_used=model_name,
            provider=provider_name,
            tokens_used=tokens_used,
            source="local"
        )

    async def _call_remote_llm(
        self,
        remote_agent: str,
        prompt: str,
        system_message: str,
        timeout: float,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> LLMCallResult:
        """Delegate LLM call to a remote agent."""
        
        # Discover remote agent capabilities
        capabilities = await discover_agent(remote_agent, timeout)
        if not capabilities:
            raise ValueError(f"Cannot discover remote agent at {remote_agent}")
        
        PrintStyle(font_color="#85C1E9").print(
            f"Delegating to {capabilities.protocol} agent: {capabilities.agent_id or 'unknown'}"
        )
        
        # Prepare parameters for remote call
        params = {
            "prompt": prompt,
            "system_message": system_message
        }
        
        if model:
            params["model"] = model
        if max_tokens:
            params["max_tokens"] = max_tokens
        if temperature is not None:
            params["temperature"] = temperature
        
        # Create agent bridge for the call
        bridge = AgentBridge(
            agent=self.agent,
            name="agent_bridge",
            method=None,
            args={
                "endpoint": remote_agent,
                "action": "call",
                "method": "llm_call",  # Standard method for LLM calls
                "params": json.dumps(params),
                "timeout": str(timeout)
            },
            message="",
            loop_data=self.loop_data
        )
        
        # Execute the remote call
        bridge_response = await bridge.execute()
        
        if "Error:" in bridge_response.message:
            raise ValueError(f"Remote LLM call failed: {bridge_response.message}")
        
        # Parse the response
        try:
            result_data = json.loads(bridge_response.message)
            remote_response = result_data.get("response", {})
            
            if capabilities.protocol == "A2A":
                # A2A JSON-RPC response format
                if "result" in remote_response:
                    llm_result = remote_response["result"]
                    response_text = llm_result.get("response", "")
                    reasoning_text = llm_result.get("reasoning", "")
                    tokens_used = llm_result.get("tokens_used", 0)
                    model_used = llm_result.get("model", model or "unknown")
                else:
                    raise ValueError("Invalid A2A response format")
            else:
                # ACP REST response format
                response_text = remote_response.get("response", "")
                reasoning_text = remote_response.get("reasoning", "")
                tokens_used = remote_response.get("tokens_used", 0)
                model_used = remote_response.get("model", model or "unknown")
            
            return LLMCallResult(
                response=response_text,
                reasoning=reasoning_text,
                model_used=model_used,
                provider="remote",
                tokens_used=tokens_used,
                source="remote",
                remote_agent=remote_agent
            )
            
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Failed to parse remote LLM response: {str(e)}")

    def _get_provider_concurrency(self, provider: str) -> int:
        """Get concurrency limit for a provider."""
        # Default concurrency limits based on common provider patterns
        provider_limits = {
            "openai": 10,
            "anthropic": 5,
            "openrouter": 8,
            "local": 3,
            "other": 5
        }
        return provider_limits.get(provider.lower(), 5)

    def _parse_int(self, value: Optional[str]) -> Optional[int]:
        """Safely parse integer from string."""
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _parse_float(self, value: str) -> float:
        """Safely parse float from string."""
        try:
            return float(value)
        except ValueError:
            return 0.7

    def _parse_bool(self, value: str) -> bool:
        """Parse boolean value from string."""
        return value.lower() in ("true", "1", "yes", "on")

    def _format_response(self, result: LLMCallResult) -> Response:
        """Format the LLM result into a tool response."""
        response_data = {
            "response": result.response,
            "model_used": result.model_used,
            "provider": result.provider,
            "source": result.source,
            "tokens_used": result.tokens_used,
            "duration": round(result.duration, 3)
        }
        
        if result.reasoning:
            response_data["reasoning"] = result.reasoning
        
        if result.remote_agent:
            response_data["remote_agent"] = result.remote_agent
        
        # Log summary
        summary = (
            f"LLM call completed: {result.model_used} ({result.source}) "
            f"- {result.tokens_used} tokens in {result.duration:.3f}s"
        )
        PrintStyle(font_color="green", bold=True).print(summary)
        
        # For simple use cases, return just the response text
        # For complex use cases, return the full JSON structure
        if self.args.get("format", "simple") == "detailed":
            return Response(
                message=json.dumps(response_data, indent=2),
                break_loop=False
            )
        else:
            return Response(
                message=result.response,
                break_loop=False
            )

    async def before_execution(self, **kwargs):
        """Override to provide custom logging for LLM calls."""
        PrintStyle(font_color="#1B4F72", padding=True, background_color="white", bold=True).print(
            f"{self.agent.agent_name}: Using tool 'llm_bridge'"
        )
        self.log = self.get_log_object()
        
        # Log key parameters
        prompt = self.args.get("prompt", "")
        remote_agent = self.args.get("remote_agent", "")
        model = self.args.get("model", "default")
        
        PrintStyle(font_color="#85C1E9", bold=True).stream("Prompt: ")
        PrintStyle(font_color="#85C1E9", padding=True).print(prompt[:100] + "..." if len(prompt) > 100 else prompt)
        
        if remote_agent:
            PrintStyle(font_color="#85C1E9", bold=True).stream("Remote agent: ")
            PrintStyle(font_color="#85C1E9").print(remote_agent)
        
        PrintStyle(font_color="#85C1E9", bold=True).stream("Model: ")
        PrintStyle(font_color="#85C1E9").print(model)


# Utility functions for common LLM operations

async def quick_llm_call(
    agent, 
    prompt: str, 
    system_message: str = "",
    model: Optional[str] = None,
    **kwargs
) -> str:
    """
    Quick utility function for simple LLM calls.
    
    Args:
        agent: Agent instance
        prompt: User prompt
        system_message: Optional system message
        model: Optional model override
        **kwargs: Additional parameters
        
    Returns:
        LLM response as string
    """
    bridge = LLMBridge(
        agent=agent,
        name="llm_bridge",
        method=None,
        args={
            "prompt": prompt,
            "system_message": system_message,
            "model": model or "",
            **{k: str(v) for k, v in kwargs.items()}
        },
        message="",
        loop_data=None
    )
    
    response = await bridge.execute()
    return response.message


def create_llm_operation(
    prompt: str,
    system_message: str = "",
    model: Optional[str] = None,
    remote_agent: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Create an LLM operation for use with ParallelExecutor.
    
    Args:
        prompt: User prompt
        system_message: Optional system message
        model: Optional model name
        remote_agent: Optional remote agent endpoint
        **kwargs: Additional parameters
        
    Returns:
        Operation dictionary for parallel execution
    """
    return {
        "type": "llm_call",
        "prompt": prompt,
        "system_message": system_message,
        "model": model,
        "remote_agent": remote_agent,
        **kwargs
    }