import asyncio
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from python.helpers.extension import Extension
from python.tools.parallel_executor import ParallelExecutor
from python.tools.agent_bridge import discover_agent, AgentCapabilities
from agent import Agent, LoopData


@dataclass
class SubAgentInfo:
    """Information about a registered subordinate agent."""
    agent_id: str
    endpoint: str
    capabilities: Optional[AgentCapabilities] = None
    last_contact: Optional[datetime] = None
    status: str = "unknown"  # "online", "offline", "busy", "unknown"
    task_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


DATA_NAME_SUB_AGENTS = "sub_agents_registry"
DATA_NAME_SUB_AGENT_TASKS = "sub_agent_tasks"


class SubAgentManager(Extension):
    """
    Extension for managing subordinate agents in a multi-agent hierarchy.
    
    This extension provides capabilities for:
    - Registering and discovering subordinate agents
    - Broadcasting tasks to multiple agents
    - Managing agent lifecycle and status
    - Coordinating parallel agent operations
    """

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        """
        Execute sub-agent management tasks during message loop start.
        
        This method:
        1. Updates status of registered sub-agents
        2. Processes any pending sub-agent communications
        3. Manages agent discovery and registration
        """
        # Initialize sub-agent registry if not exists
        if not self.agent.get_data(DATA_NAME_SUB_AGENTS):
            self.agent.set_data(DATA_NAME_SUB_AGENTS, {})
        
        if not self.agent.get_data(DATA_NAME_SUB_AGENT_TASKS):
            self.agent.set_data(DATA_NAME_SUB_AGENT_TASKS, [])
        
        # Update agent status periodically
        iteration_no = loop_data.iteration
        if iteration_no % 10 == 0:  # Every 10 iterations
            await self._update_agent_status()
        
        # Discover new agents on network (less frequently)
        if iteration_no % 50 == 0:  # Every 50 iterations
            await self._discover_network_agents()
        
        # Process any pending sub-agent tasks
        await self._process_pending_tasks()

    async def _update_agent_status(self):
        """Update the status of all registered sub-agents."""
        registry = self.agent.get_data(DATA_NAME_SUB_AGENTS) or {}
        
        if not registry:
            return
        
        # Update status for each registered agent
        for agent_id, info_data in registry.items():
            info = SubAgentInfo(**info_data)
            try:
                # Quick ping to check if agent is responsive
                capabilities = await discover_agent(info.endpoint, timeout=5.0)
                if capabilities:
                    info.status = "online"
                    info.capabilities = capabilities
                    info.last_contact = datetime.now(timezone.utc)
                else:
                    info.status = "offline"
            except Exception:
                info.status = "offline"
            
            # Update registry with new info
            registry[agent_id] = info.__dict__
        
        self.agent.set_data(DATA_NAME_SUB_AGENTS, registry)

    async def _discover_network_agents(self):
        """Discover agents on the network using common endpoints and protocols."""
        from python.helpers.print_style import PrintStyle
        
        # List of potential agent endpoints to check
        discovery_endpoints = [
            "http://localhost:8001",
            "http://localhost:8002", 
            "http://localhost:8003",
            "http://127.0.0.1:8001",
            "http://127.0.0.1:8002",
            "http://127.0.0.1:8003",
        ]
        
        # Get current registry
        registry = self.agent.get_data(DATA_NAME_SUB_AGENTS) or {}
        
        PrintStyle(font_color="#2E86AB").print("Discovering agents on network...")
        
        discovered_count = 0
        for endpoint in discovery_endpoints:
            try:
                # Skip if already registered
                existing_agent = next(
                    (info for info in registry.values() if info.get("endpoint") == endpoint),
                    None
                )
                if existing_agent:
                    continue
                
                # Try to discover agent at this endpoint
                capabilities = await discover_agent(endpoint, timeout=3.0)
                if capabilities:
                    # Create agent ID from endpoint
                    agent_id = f"agent_{endpoint.split(':')[-1]}"
                    
                    # Ensure unique agent ID
                    counter = 1
                    original_id = agent_id
                    while agent_id in registry:
                        agent_id = f"{original_id}_{counter}"
                        counter += 1
                    
                    # Register the discovered agent
                    info = SubAgentInfo(
                        agent_id=agent_id,
                        endpoint=endpoint,
                        capabilities=capabilities,
                        status="online",
                        last_contact=datetime.now(timezone.utc)
                    )
                    
                    registry[agent_id] = info.__dict__
                    discovered_count += 1
                    
                    PrintStyle(font_color="green").print(
                        f"Discovered {capabilities.protocol} agent: {agent_id} at {endpoint}"
                    )
                    
            except Exception as e:
                # Silently skip failed discoveries
                pass
        
        if discovered_count > 0:
            self.agent.set_data(DATA_NAME_SUB_AGENTS, registry)
            PrintStyle(font_color="green").print(f"Discovered {discovered_count} new agents")
        
    async def _process_pending_tasks(self):
        """Process any pending sub-agent tasks."""
        tasks = self.agent.get_data(DATA_NAME_SUB_AGENT_TASKS) or []
        
        if not tasks:
            return
        
        # Process tasks (this could be extended for more complex task management)
        processed_tasks = []
        for task in tasks:
            if task.get("status") == "pending":
                # Task processing logic would go here
                task["status"] = "processed"
                task["processed_at"] = datetime.now(timezone.utc).isoformat()
            
            processed_tasks.append(task)
        
        self.agent.set_data(DATA_NAME_SUB_AGENT_TASKS, processed_tasks)


# Utility functions for sub-agent management

def register_sub_agent(agent: Agent, agent_id: str, endpoint: str) -> bool:
    """
    Register a subordinate agent with the current agent.
    
    Args:
        agent: The parent agent
        agent_id: Unique identifier for the sub-agent
        endpoint: Network endpoint for the sub-agent
        
    Returns:
        True if registration successful, False otherwise
    """
    registry = agent.get_data(DATA_NAME_SUB_AGENTS) or {}
    
    if agent_id in registry:
        return False  # Agent already registered
    
    info = SubAgentInfo(
        agent_id=agent_id,
        endpoint=endpoint,
        status="unknown"
    )
    
    registry[agent_id] = info.__dict__
    agent.set_data(DATA_NAME_SUB_AGENTS, registry)
    
    return True


def unregister_sub_agent(agent: Agent, agent_id: str) -> bool:
    """
    Unregister a subordinate agent.
    
    Args:
        agent: The parent agent
        agent_id: Unique identifier for the sub-agent
        
    Returns:
        True if unregistration successful, False if agent not found
    """
    registry = agent.get_data(DATA_NAME_SUB_AGENTS) or {}
    
    if agent_id not in registry:
        return False
    
    del registry[agent_id]
    agent.set_data(DATA_NAME_SUB_AGENTS, registry)
    
    return True


def get_sub_agents(agent: Agent) -> List[SubAgentInfo]:
    """
    Get list of all registered subordinate agents.
    
    Args:
        agent: The parent agent
        
    Returns:
        List of SubAgentInfo objects
    """
    registry = agent.get_data(DATA_NAME_SUB_AGENTS) or {}
    return [SubAgentInfo(**info_data) for info_data in registry.values()]


def get_online_sub_agents(agent: Agent) -> List[SubAgentInfo]:
    """
    Get list of online subordinate agents.
    
    Args:
        agent: The parent agent
        
    Returns:
        List of online SubAgentInfo objects
    """
    return [info for info in get_sub_agents(agent) if info.status == "online"]


async def broadcast_to_sub_agents(
    agent: Agent,
    message: str,
    agent_ids: Optional[List[str]] = None,
    timeout: float = 30.0
) -> Dict[str, Any]:
    """
    Broadcast a message to multiple subordinate agents in parallel.
    
    Args:
        agent: The parent agent
        message: Message to broadcast
        agent_ids: Specific agent IDs to target (None for all online agents)
        timeout: Timeout for each agent call
        
    Returns:
        Dictionary mapping agent_id to response
    """
    registry = agent.get_data(DATA_NAME_SUB_AGENTS) or {}
    
    # Determine target agents
    if agent_ids:
        targets = [
            SubAgentInfo(**registry[aid]) 
            for aid in agent_ids 
            if aid in registry
        ]
    else:
        targets = get_online_sub_agents(agent)
    
    if not targets:
        return {}
    
    # Create parallel operations for broadcast
    operations = []
    for info in targets:
        operations.append({
            "type": "agent_call",
            "message": message,
            "endpoint": info.endpoint,
            "agent_id": info.agent_id,
            "timeout": timeout
        })
    
    # Execute broadcast using ParallelExecutor
    executor = ParallelExecutor(
        agent=agent,
        name="parallel_executor",
        method=None,
        args={
            "operations": json.dumps(operations),
            "max_concurrency": min(len(operations), 5),
            "timeout": str(timeout),
            "fail_fast": "false"
        },
        message="",
        loop_data=None
    )
    
    response = await executor.execute()
    
    # Parse response and map back to agent IDs
    try:
        result_data = json.loads(response.message)
        results = {}
        
        for i, result in enumerate(result_data.get("results", [])):
            if i < len(targets):
                agent_id = targets[i].agent_id
                results[agent_id] = {
                    "success": result["success"],
                    "response": result.get("result"),
                    "error": result.get("error"),
                    "duration": result.get("duration", 0)
                }
        
        return results
        
    except (json.JSONDecodeError, KeyError):
        return {}


async def await_sub_agent_responses(
    agent: Agent,
    task_id: str,
    expected_agents: List[str],
    timeout: float = 60.0
) -> Dict[str, Any]:
    """
    Wait for responses from specific subordinate agents.
    
    This function implements the "await" pattern for coordinating
    multi-agent tasks where responses are expected.
    
    Args:
        agent: The parent agent
        task_id: Unique identifier for the task
        expected_agents: List of agent IDs expected to respond
        timeout: Maximum time to wait for responses
        
    Returns:
        Dictionary mapping agent_id to response data
    """
    responses = {}
    start_time = asyncio.get_event_loop().time()
    
    while len(responses) < len(expected_agents):
        current_time = asyncio.get_event_loop().time()
        if current_time - start_time > timeout:
            break
        
        # Check for new responses from sub-agent task queue
        tasks = agent.get_data(DATA_NAME_SUB_AGENT_TASKS) or []
        
        for task in tasks:
            if (task.get("task_id") == task_id and 
                task.get("agent_id") in expected_agents and
                task.get("agent_id") not in responses and
                task.get("status") == "completed"):
                
                responses[task["agent_id"]] = task.get("response_data", {})
        
        if len(responses) < len(expected_agents):
            await asyncio.sleep(0.5)
    
    return responses


def add_sub_agent_task(
    agent: Agent,
    task_id: str,
    agent_id: str,
    task_data: Dict[str, Any]
) -> None:
    """
    Add a task to the sub-agent task queue.
    
    Args:
        agent: The parent agent
        task_id: Unique identifier for the task
        agent_id: Target agent ID
        task_data: Task data dictionary
    """
    tasks = agent.get_data(DATA_NAME_SUB_AGENT_TASKS) or []
    
    task = {
        "task_id": task_id,
        "agent_id": agent_id,
        "task_data": task_data,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    tasks.append(task)
    agent.set_data(DATA_NAME_SUB_AGENT_TASKS, tasks)


def complete_sub_agent_task(
    agent: Agent,
    task_id: str,
    agent_id: str,
    response_data: Dict[str, Any]
) -> None:
    """
    Mark a sub-agent task as completed with response data.
    
    Args:
        agent: The parent agent
        task_id: Task identifier
        agent_id: Agent that completed the task
        response_data: Response data from the agent
    """
    tasks = agent.get_data(DATA_NAME_SUB_AGENT_TASKS) or []
    
    for task in tasks:
        if (task.get("task_id") == task_id and 
            task.get("agent_id") == agent_id):
            task["status"] = "completed"
            task["response_data"] = response_data
            task["completed_at"] = datetime.now(timezone.utc).isoformat()
            break
    
    agent.set_data(DATA_NAME_SUB_AGENT_TASKS, tasks)


def get_agent_statistics(agent: Agent) -> Dict[str, Any]:
    """
    Get statistics about subordinate agents.
    
    Args:
        agent: The parent agent
        
    Returns:
        Dictionary with agent statistics
    """
    registry = agent.get_data(DATA_NAME_SUB_AGENTS) or {}
    tasks = agent.get_data(DATA_NAME_SUB_AGENT_TASKS) or []
    
    status_counts = {}
    total_tasks = 0
    
    for info_data in registry.values():
        info = SubAgentInfo(**info_data)
        status_counts[info.status] = status_counts.get(info.status, 0) + 1
        total_tasks += info.task_count
    
    return {
        "total_agents": len(registry),
        "status_counts": status_counts,
        "total_tasks": total_tasks,
        "pending_tasks": len([t for t in tasks if t.get("status") == "pending"]),
        "online_agents": status_counts.get("online", 0)
    }