import asyncio
import json
import time
from typing import List, Dict, Any, Coroutine, Optional
from dataclasses import dataclass

from python.helpers.tool import Tool, Response
from python.helpers.concurrency_limiter import ConcurrencyLimiter
from python.helpers.print_style import PrintStyle


@dataclass
class ParallelResult:
    """Result from a parallel execution operation."""
    index: int
    result: Any
    success: bool
    error: Optional[str] = None
    duration: float = 0.0


class ParallelExecutor(Tool):
    """
    Tool for executing multiple operations in parallel with concurrency control.
    
    This tool leverages asyncio.TaskGroup for robust parallel execution and integrates
    with Agent Zero's concurrency limiting system to prevent rate limit violations.
    
    Supports both simple coroutine execution and complex multi-agent communication patterns.
    """

    async def execute(self, **kwargs) -> Response:
        """
        Execute multiple operations in parallel.
        
        Args (via self.args):
            operations: List of operation definitions
            max_concurrency: Maximum concurrent operations (optional)
            timeout: Timeout for all operations in seconds (optional)
            fail_fast: Whether to stop on first error (optional, default: False)
            
        Returns:
            Response containing execution results
        """
        try:
            operations = self._parse_operations()
            max_concurrency = int(self.args.get("max_concurrency", 5))
            timeout = float(self.args.get("timeout", 60.0))
            fail_fast = self._parse_bool(self.args.get("fail_fast", "false"))
            
            PrintStyle(font_color="#2E86AB", bold=True).print(
                f"Executing {len(operations)} operations in parallel (max_concurrency={max_concurrency})"
            )
            
            start_time = time.time()
            results = await self._execute_parallel(
                operations, max_concurrency, timeout, fail_fast
            )
            total_duration = time.time() - start_time
            
            return self._format_response(results, total_duration)
            
        except Exception as e:
            error_msg = f"Parallel execution failed: {str(e)}"
            PrintStyle(font_color="red", bold=True).print(error_msg)
            return Response(message=error_msg, break_loop=False)

    def _parse_operations(self) -> List[Dict[str, Any]]:
        """Parse operations from the arguments."""
        operations_arg = self.args.get("operations", "[]")
        
        if isinstance(operations_arg, str):
            try:
                operations = json.loads(operations_arg)
            except json.JSONDecodeError:
                # Try to parse as a simple list of strings
                operations = [{"type": "simple", "data": op.strip()} 
                            for op in operations_arg.split(",") if op.strip()]
        elif isinstance(operations_arg, list):
            operations = operations_arg
        else:
            operations = []
            
        if not operations:
            raise ValueError("No operations provided")
            
        return operations

    def _parse_bool(self, value) -> bool:
        """Parse boolean value from string or bool."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    async def _execute_parallel(
        self, 
        operations: List[Dict[str, Any]], 
        max_concurrency: int,
        timeout: float,
        fail_fast: bool
    ) -> List[ParallelResult]:
        """Execute operations in parallel using TaskGroup."""
        results = []
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def _execute_single(index: int, operation: Dict[str, Any]) -> ParallelResult:
            """Execute a single operation with concurrency control."""
            async with semaphore:
                start_time = time.time()
                try:
                    result = await self._execute_operation(operation)
                    duration = time.time() - start_time
                    return ParallelResult(
                        index=index, 
                        result=result, 
                        success=True, 
                        duration=duration
                    )
                except Exception as e:
                    duration = time.time() - start_time
                    error_msg = str(e)
                    PrintStyle(font_color="orange").print(
                        f"Operation {index} failed: {error_msg}"
                    )
                    return ParallelResult(
                        index=index, 
                        result=None, 
                        success=False, 
                        error=error_msg,
                        duration=duration
                    )
        
        try:
            async with asyncio.timeout(timeout):
                if fail_fast:
                    # Use TaskGroup for fail-fast behavior
                    async with asyncio.TaskGroup() as tg:
                        tasks = [
                            tg.create_task(_execute_single(i, op))
                            for i, op in enumerate(operations)
                        ]
                    results = [task.result() for task in tasks]
                else:
                    # Use gather with return_exceptions for resilient execution
                    tasks = [_execute_single(i, op) for i, op in enumerate(operations)]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Convert exceptions to ParallelResult objects
                    processed_results = []
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            processed_results.append(ParallelResult(
                                index=i,
                                result=None,
                                success=False,
                                error=str(result),
                                duration=0.0
                            ))
                        else:
                            processed_results.append(result)
                    results = processed_results
                    
        except asyncio.TimeoutError:
            error_msg = f"Parallel execution timed out after {timeout} seconds"
            PrintStyle(font_color="red").print(error_msg)
            # Return timeout results for completed operations
            results.extend([
                ParallelResult(
                    index=i,
                    result=None,
                    success=False,
                    error="Timeout",
                    duration=timeout
                ) for i in range(len(results), len(operations))
            ])
        
        return results

    async def _execute_operation(self, operation: Dict[str, Any]) -> Any:
        """Execute a single operation based on its type."""
        op_type = operation.get("type", "simple")
        
        if op_type == "simple":
            # Simple operation execution
            data = operation.get("data", "")
            delay = float(operation.get("delay", 0.0))
            if delay > 0:
                await asyncio.sleep(delay)
            return f"Completed: {data}"
            
        elif op_type == "agent_call":
            # Call to subordinate agent
            return await self._call_subordinate_agent(operation)
            
        elif op_type == "llm_call":
            # Direct LLM call
            return await self._call_llm(operation)
            
        elif op_type == "tool_call":
            # Call another tool
            return await self._call_tool(operation)
            
        else:
            raise ValueError(f"Unknown operation type: {op_type}")

    async def _call_subordinate_agent(self, operation: Dict[str, Any]) -> str:
        """Call a subordinate agent using the agent bridge."""
        from python.tools.agent_bridge import AgentBridge
        
        message = operation.get("message", "")
        endpoint = operation.get("endpoint", "")
        timeout = operation.get("timeout", 30.0)
        
        if not endpoint:
            raise ValueError("endpoint is required for agent_call operations")
        
        # Create and execute agent bridge
        bridge = AgentBridge(
            agent=self.agent,
            name="agent_bridge",
            method=None,
            args={
                "endpoint": endpoint,
                "action": "send",
                "message": message,
                "timeout": str(timeout)
            },
            message="",
            loop_data=None
        )
        
        response = await bridge.execute()
        return response.message

    async def _call_llm(self, operation: Dict[str, Any]) -> str:
        """Make a direct LLM call using the LLM bridge."""
        from python.tools.llm_bridge import LLMBridge
        
        prompt = operation.get("prompt", "")
        model = operation.get("model", "")
        timeout = operation.get("timeout", 60.0)
        
        if not prompt:
            raise ValueError("prompt is required for llm_call operations")
        
        # Create and execute LLM bridge
        llm_bridge = LLMBridge(
            agent=self.agent,
            name="llm_bridge",
            method="call",
            args={
                "prompt": prompt,
                "model": model,
                "timeout": str(timeout)
            },
            message="",
            loop_data=None
        )
        
        response = await llm_bridge.execute()
        return response.message

    async def _call_tool(self, operation: Dict[str, Any]) -> str:
        """Call another Agent Zero tool."""
        tool_name = operation.get("tool_name", "")
        tool_args = operation.get("args", {})
        method = operation.get("method", "execute")
        
        if not tool_name:
            raise ValueError("tool_name is required for tool_call operations")
        
        # Import and instantiate the tool dynamically
        try:
            # Import the tool module
            module_path = f"python.tools.{tool_name}"
            module = __import__(module_path, fromlist=[tool_name])
            
            # Get the tool class (assume it's the capitalized version of tool_name)
            tool_class_name = ''.join(word.capitalize() for word in tool_name.split('_'))
            tool_class = getattr(module, tool_class_name)
            
            # Create tool instance
            tool_instance = tool_class(
                agent=self.agent,
                name=tool_name,
                method=method,
                args=tool_args,
                message="",
                loop_data=None
            )
            
            # Execute the tool
            response = await tool_instance.execute()
            return response.message
            
        except Exception as e:
            raise ValueError(f"Failed to execute tool {tool_name}: {str(e)}")

    def _format_response(self, results: List[ParallelResult], total_duration: float) -> Response:
        """Format the parallel execution results into a response."""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        response_data = {
            "total_operations": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "total_duration": round(total_duration, 3),
            "results": []
        }
        
        for result in results:
            response_data["results"].append({
                "index": result.index,
                "success": result.success,
                "result": result.result,
                "error": result.error,
                "duration": round(result.duration, 3)
            })
        
        if failed:
            response_data["errors"] = [
                {"index": r.index, "error": r.error} for r in failed
            ]
        
        summary = (
            f"Parallel execution completed: {len(successful)}/{len(results)} successful "
            f"in {total_duration:.3f}s"
        )
        
        if failed:
            summary += f", {len(failed)} failed"
        
        PrintStyle(font_color="green" if not failed else "orange", bold=True).print(summary)
        
        # Format as JSON for structured response
        formatted_response = json.dumps(response_data, indent=2)
        
        return Response(message=formatted_response, break_loop=False)

    async def before_execution(self, **kwargs):
        """Override to provide custom logging for parallel operations."""
        PrintStyle(font_color="#1B4F72", padding=True, background_color="white", bold=True).print(
            f"{self.agent.agent_name}: Using tool 'parallel_executor'"
        )
        self.log = self.get_log_object()
        
        # Log operation count and concurrency settings
        operations = self._parse_operations()
        max_concurrency = int(self.args.get("max_concurrency", 5))
        
        PrintStyle(font_color="#85C1E9", bold=True).stream("Operations: ")
        PrintStyle(font_color="#85C1E9").print(f"{len(operations)}")
        
        PrintStyle(font_color="#85C1E9", bold=True).stream("Max concurrency: ")
        PrintStyle(font_color="#85C1E9").print(f"{max_concurrency}")


# Utility functions for creating parallel operations

def create_simple_operation(data: str, delay: float = 0.1) -> Dict[str, Any]:
    """Create a simple operation for testing."""
    return {
        "type": "simple",
        "data": data,
        "delay": delay
    }

def create_agent_operation(message: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Create an agent call operation."""
    return {
        "type": "agent_call",
        "message": message,
        "agent_id": agent_id
    }

def create_llm_operation(prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
    """Create an LLM call operation."""
    return {
        "type": "llm_call",
        "prompt": prompt,
        "model": model
    }

def create_tool_operation(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Create a tool call operation."""
    return {
        "type": "tool_call",
        "tool_name": tool_name,
        "args": args
    }