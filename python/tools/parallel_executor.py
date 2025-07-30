import asyncio
import json
import time
import uuid
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
        Execute multiple operations in parallel with flow tracking.
        
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
            
            # Create flow tracking
            flow_id = str(uuid.uuid4())
            task_description = self._extract_task_description(operations)
            
            from python.api.agent_flow import flow_tracker
            flow_tracker.create_flow(
                flow_id=flow_id,
                parent_agent=getattr(self.agent, 'agent_name', 'main'),
                task_description=task_description
            )
            
            PrintStyle(font_color="#2E86AB", bold=True).print(
                f"Executing {len(operations)} operations in parallel (Flow ID: {flow_id[:8]}...)"
            )
            
            start_time = time.time()
            results = await self._execute_parallel(
                operations, max_concurrency, timeout, fail_fast, flow_id
            )
            total_duration = time.time() - start_time
            
            # Complete flow tracking
            success = sum(1 for r in results if r.success) > 0
            flow_tracker.complete_flow(flow_id, success)
            
            return self._format_response(results, total_duration, flow_id)
            
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

    def _extract_task_description(self, operations: List[Dict[str, Any]]) -> str:
        """Extract a meaningful task description from operations."""
        if not operations:
            return "Parallel execution task"
        
        # Try to identify the main task from agent_call messages
        agent_calls = [op for op in operations if op.get("type") == "agent_call"]
        if agent_calls:
            first_message = agent_calls[0].get("message", "")
            if len(first_message) > 100:
                return first_message[:97] + "..."
            return first_message or "Multi-agent collaboration task"
        
        return f"Parallel execution of {len(operations)} operations"

    async def _execute_parallel(
        self, 
        operations: List[Dict[str, Any]], 
        max_concurrency: int,
        timeout: float,
        fail_fast: bool,
        flow_id: str
    ) -> List[ParallelResult]:
        """Execute operations in parallel using TaskGroup with flow tracking."""
        results = []
        semaphore = asyncio.Semaphore(max_concurrency)
        
        from python.api.agent_flow import flow_tracker
        
        # Initialize flow progress
        flow_tracker.update_flow_progress(flow_id, 0, len(operations))
        
        async def _execute_single(index: int, operation: Dict[str, Any]) -> ParallelResult:
            """Execute a single operation with concurrency control and tracking."""
            async with semaphore:
                start_time = time.time()
                agent_id = f"agent_{index}_{int(start_time)}"
                
                try:
                    # Add agent to flow tracking with enhanced information
                    agent_role = self._extract_agent_role(operation)
                    agent_info = {
                        "id": agent_id,
                        "name": agent_role,
                        "type": agent_role.lower().replace(" ", "_"),
                        "role": agent_role,
                        "status": "running",
                        "message": operation.get("message", ""),
                        "endpoint": operation.get("endpoint", "local"),
                        "protocol": "local",
                        # Hierarchical relationship information
                        "parent_id": getattr(self.agent, 'agent_id', None) if hasattr(self.agent, 'agent_id') else None,
                        "superior_id": getattr(self.agent, 'agent_id', None) if hasattr(self.agent, 'agent_id') else None,
                        "hierarchy_level": 1 if operation.get("type") == "subordinate" else 0
                    }

                    # If this is a network agent operation, try to get Agent Card info
                    if operation.get("endpoint"):
                        try:
                            from python.tools.agent_bridge import discover_agent
                            discovered_info = await discover_agent(operation["endpoint"], timeout=3.0)
                            if discovered_info:
                                agent_info.update({
                                    "agent_card": discovered_info.get("agent_card", {}),
                                    "skills": discovered_info.get("skills", []),
                                    "capabilities": discovered_info.get("capabilities", {}),
                                    "protocol": discovered_info.get("protocol", "unknown"),
                                    "version": discovered_info.get("version", "unknown"),
                                    "description": discovered_info.get("description", ""),
                                    "name": discovered_info.get("name", agent_role)
                                })
                        except Exception as e:
                            # If discovery fails, continue with basic info
                            pass

                    flow_tracker.add_agent_to_flow(flow_id, agent_info)
                    
                    # Register subordinate agent in the global agent registry
                    from python.api.agents_list import register_subordinate_agent
                    register_subordinate_agent(agent_id, {
                        "name": f"@{agent_role.lower().replace(' ', '_')}",
                        "role": agent_role,
                        "status": "working", 
                        "parent_agent": getattr(self.agent, 'agent_name', 'main'),
                        "profile": agent_role.lower().replace(' ', '_'),
                        "endpoint": f"local://{agent_id}",
                        "task_count": 1
                    })
                    
                    # Execute operation
                    result = await self._execute_operation(operation, flow_id, agent_id)
                    duration = time.time() - start_time
                    
                    # Update agent status
                    flow_tracker.update_agent_status(flow_id, agent_id, "completed", 100)
                    
                    # Update agent registry status
                    from python.api.agents_list import update_subordinate_agent
                    update_subordinate_agent(agent_id, {
                        "status": "idle",
                        "task_count": 0
                    })
                    
                    # Update flow progress
                    completed = sum(1 for r in results if r.success) + 1
                    flow_tracker.update_flow_progress(flow_id, completed, len(operations))
                    
                    return ParallelResult(
                        index=index, 
                        result=result, 
                        success=True, 
                        duration=duration
                    )
                except Exception as e:
                    duration = time.time() - start_time
                    error_msg = str(e)
                    
                    # Update agent status as failed
                    flow_tracker.update_agent_status(flow_id, agent_id, "failed", 0)
                    
                    # Update agent registry status
                    from python.api.agents_list import update_subordinate_agent
                    update_subordinate_agent(agent_id, {
                        "status": "error",
                        "task_count": 0
                    })
                    
                    PrintStyle(font_color="orange").print(
                        f"Operation {index} ({agent_role}) failed: {error_msg}"
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

    def _extract_agent_role(self, operation: Dict[str, Any]) -> str:
        """Extract agent role from operation message."""
        message = operation.get("message", "")
        
        # Common role patterns
        role_patterns = {
            "ui/ux designer": "UI/UX Designer",
            "frontend developer": "Frontend Developer", 
            "backend developer": "Backend Developer",
            "content writer": "Content Writer",
            "marketing strategist": "Marketing Strategist",
            "qa tester": "QA Tester",
            "devops": "DevOps Engineer"
        }
        
        message_lower = message.lower()
        for pattern, role in role_patterns.items():
            if pattern in message_lower:
                return role
        
        # Fallback to operation type or generic name
        op_type = operation.get("type", "unknown")
        if op_type == "agent_call":
            return "Specialist Agent"
        elif op_type == "llm_call":
            return "LLM Assistant"
        elif op_type == "tool_call":
            return "Tool Agent"
        else:
            return "Worker Agent"

    async def _execute_operation(self, operation: Dict[str, Any], flow_id: str = None, agent_id: str = None) -> Any:
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
        """Call a subordinate agent - try discovered agents first, fallback to local subagents."""
        message = operation.get("message", "")
        endpoint = operation.get("endpoint", "")
        profile = operation.get("profile", "default")
        timeout = operation.get("timeout", 30.0)
        
        # If endpoint specified, use agent_bridge for network communication
        if endpoint:
            return await self._call_network_agent(endpoint, message, timeout)
        
        # Try to discover available agents using ACP/A2A protocols
        discovered_agent = await self._discover_available_agent()
        if discovered_agent:
            PrintStyle(font_color="cyan").print(f"Using discovered agent: {discovered_agent}")
            return await self._call_network_agent(discovered_agent, message, timeout)
        
        # Fallback to local subagent delegation
        PrintStyle(font_color="yellow").print("No network agents discovered, spawning local subagent")
        return await self._call_local_subagent(message, profile)

    async def _discover_available_agent(self) -> str:
        """Discover available agents using ACP/A2A protocols."""
        import aiohttp
        
        # Check common agent ports for ACP/A2A agents
        discovery_ports = [8001, 8002, 8003, 8004, 8005]
        
        for port in discovery_ports:
            # Try ACP discovery first
            acp_endpoint = f"http://localhost:{port}"
            try:
                async with aiohttp.ClientSession() as session:
                    # ACP ping endpoint
                    async with session.get(f"{acp_endpoint}/acp_ping", timeout=aiohttp.ClientTimeout(total=1)) as response:
                        if response.status == 200:
                            return acp_endpoint
            except:
                pass
            
            # Try A2A discovery
            try:
                async with aiohttp.ClientSession() as session:
                    # A2A getAgentCard RPC call
                    rpc_request = {
                        "jsonrpc": "2.0",
                        "method": "getAgentCard", 
                        "params": {},
                        "id": 1
                    }
                    async with session.post(
                        f"http://localhost:{port}/rpc",
                        json=rpc_request,
                        timeout=aiohttp.ClientTimeout(total=1),
                        headers={"Content-Type": "application/json"}
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            if "result" in result:
                                return f"http://localhost:{port}"
            except:
                pass
        
        return ""  # No agents discovered

    async def _call_network_agent(self, endpoint: str, message: str, timeout: float) -> str:
        """Call a network agent using agent_bridge."""
        from python.tools.agent_bridge import AgentBridge
        
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

    async def _call_local_subagent(self, message: str, profile: str) -> str:
        """Spawn and call a local subagent."""
        from python.tools.call_subordinate import CallSubordinate
        
        subordinate = CallSubordinate(
            agent=self.agent,
            name="call_subordinate",
            method=None,
            args={
                "profile": profile,
                "message": message,
                "reset": "false"
            },
            message="",
            loop_data=None
        )
        
        response = await subordinate.execute()
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

    def _format_response(self, results: List[ParallelResult], total_duration: float, flow_id: str = None) -> Response:
        """Format the parallel execution results into a response."""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        response_data = {
            "total_operations": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "total_duration": round(total_duration, 3),
            "flow_id": flow_id,
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