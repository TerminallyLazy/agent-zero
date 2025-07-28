import asyncio
import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from python.helpers.extension import Extension
from agent import Agent, LoopData


class SessionState(Enum):
    """ACP session states."""
    IDLE = "idle"
    ACTIVE = "active"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskState(Enum):
    """A2A task states."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ACPSession:
    """Represents an ACP session."""
    session_id: str
    endpoint: str
    state: SessionState = SessionState.IDLE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: Dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    timeout: float = 300.0  # 5 minutes default


@dataclass 
class A2ATask:
    """Represents an A2A task."""
    task_id: str
    endpoint: str
    state: TaskState = TaskState.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


DATA_NAME_ACP_SESSIONS = "acp_sessions"
DATA_NAME_A2A_TASKS = "a2a_tasks"
DATA_NAME_SESSION_STATS = "session_stats"


class LLMSessionManager(Extension):
    """
    Extension for managing ACP sessions and A2A task continuity.
    
    This extension handles:
    - ACP session lifecycle management
    - A2A task state tracking and continuity
    - Session timeout and cleanup
    - Context preservation across calls
    - Statistics and monitoring
    """

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        """
        Execute session management tasks during monologue start.
        
        This method:
        1. Initializes session storage if needed
        2. Cleans up expired sessions and tasks
        3. Updates session statistics
        4. Manages session lifecycle
        """
        # Initialize session storage
        self._initialize_storage()
        
        # Clean up expired sessions and tasks
        await self._cleanup_expired()
        
        # Update session statistics
        self._update_statistics()
        
        # Log session activity periodically
        iteration_no = getattr(loop_data, 'iteration', 0)
        if iteration_no % 20 == 0:  # Every 20 iterations
            self._log_session_summary()

    def _initialize_storage(self):
        """Initialize session storage if not exists."""
        if not self.agent.get_data(DATA_NAME_ACP_SESSIONS):
            self.agent.set_data(DATA_NAME_ACP_SESSIONS, {})
        
        if not self.agent.get_data(DATA_NAME_A2A_TASKS):
            self.agent.set_data(DATA_NAME_A2A_TASKS, {})
        
        if not self.agent.get_data(DATA_NAME_SESSION_STATS):
            self.agent.set_data(DATA_NAME_SESSION_STATS, {
                "total_acp_sessions": 0,
                "total_a2a_tasks": 0,
                "active_sessions": 0,
                "active_tasks": 0,
                "completed_sessions": 0,
                "completed_tasks": 0,
                "failed_sessions": 0,
                "failed_tasks": 0
            })

    async def _cleanup_expired(self):
        """Clean up expired sessions and tasks."""
        current_time = datetime.now(timezone.utc)
        
        # Clean up ACP sessions
        acp_sessions = self.agent.get_data(DATA_NAME_ACP_SESSIONS) or {}
        expired_sessions = []
        
        for session_id, session_data in acp_sessions.items():
            session = ACPSession(**session_data)
            age = (current_time - session.last_activity).total_seconds()
            
            if age > session.timeout:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del acp_sessions[session_id]
        
        if expired_sessions:
            self.agent.set_data(DATA_NAME_ACP_SESSIONS, acp_sessions)
        
        # Clean up A2A tasks (keep completed/failed for longer)
        a2a_tasks = self.agent.get_data(DATA_NAME_A2A_TASKS) or {}
        expired_tasks = []
        
        for task_id, task_data in a2a_tasks.items():
            task = A2ATask(**task_data)
            age = (current_time - task.last_update).total_seconds()
            
            # Different timeouts based on state
            if task.state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]:
                timeout = 3600  # 1 hour for completed tasks
            else:
                timeout = 1800  # 30 minutes for active tasks
            
            if age > timeout:
                expired_tasks.append(task_id)
        
        for task_id in expired_tasks:
            del a2a_tasks[task_id]
        
        if expired_tasks:
            self.agent.set_data(DATA_NAME_A2A_TASKS, a2a_tasks)

    def _update_statistics(self):
        """Update session statistics."""
        acp_sessions = self.agent.get_data(DATA_NAME_ACP_SESSIONS) or {}
        a2a_tasks = self.agent.get_data(DATA_NAME_A2A_TASKS) or {}
        
        # Count states
        acp_states = {}
        for session_data in acp_sessions.values():
            session = ACPSession(**session_data)
            acp_states[session.state.value] = acp_states.get(session.state.value, 0) + 1
        
        a2a_states = {}
        for task_data in a2a_tasks.values():
            task = A2ATask(**task_data)
            a2a_states[task.state.value] = a2a_states.get(task.state.value, 0) + 1
        
        # Update statistics
        stats = {
            "total_acp_sessions": len(acp_sessions),
            "total_a2a_tasks": len(a2a_tasks),
            "active_sessions": acp_states.get("active", 0),
            "active_tasks": a2a_states.get("running", 0) + a2a_states.get("waiting_input", 0),
            "completed_sessions": acp_states.get("completed", 0),
            "completed_tasks": a2a_states.get("completed", 0),
            "failed_sessions": acp_states.get("failed", 0),
            "failed_tasks": a2a_states.get("failed", 0),
            "acp_state_counts": acp_states,
            "a2a_state_counts": a2a_states,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        
        self.agent.set_data(DATA_NAME_SESSION_STATS, stats)

    def _log_session_summary(self):
        """Log a summary of current session activity."""
        stats = self.agent.get_data(DATA_NAME_SESSION_STATS) or {}
        
        if stats.get("total_acp_sessions", 0) > 0 or stats.get("total_a2a_tasks", 0) > 0:
            from python.helpers.print_style import PrintStyle
            
            summary = (
                f"Session Manager: {stats.get('active_sessions', 0)} ACP sessions active, "
                f"{stats.get('active_tasks', 0)} A2A tasks running"
            )
            
            PrintStyle(font_color="#8A2BE2", bold=True).print(summary)


# ACP Session Management Functions

def create_acp_session(
    agent: Agent,
    endpoint: str,
    session_id: Optional[str] = None,
    timeout: float = 300.0,
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a new ACP session.
    
    Args:
        agent: The agent instance
        endpoint: Remote agent endpoint
        session_id: Optional custom session ID
        timeout: Session timeout in seconds
        context: Initial session context
        
    Returns:
        Session ID
    """
    if not session_id:
        session_id = f"acp_{int(time.time() * 1000)}_{agent.agent_name}"
    
    session = ACPSession(
        session_id=session_id,
        endpoint=endpoint,
        timeout=timeout,
        context=context or {}
    )
    
    acp_sessions = agent.get_data(DATA_NAME_ACP_SESSIONS) or {}
    acp_sessions[session_id] = session.__dict__
    agent.set_data(DATA_NAME_ACP_SESSIONS, acp_sessions)
    
    return session_id


def get_acp_session(agent: Agent, session_id: str) -> Optional[ACPSession]:
    """
    Get an ACP session by ID.
    
    Args:
        agent: The agent instance
        session_id: Session identifier
        
    Returns:
        ACPSession if found, None otherwise
    """
    acp_sessions = agent.get_data(DATA_NAME_ACP_SESSIONS) or {}
    
    if session_id not in acp_sessions:
        return None
    
    return ACPSession(**acp_sessions[session_id])


def update_acp_session(
    agent: Agent,
    session_id: str,
    state: Optional[SessionState] = None,
    context: Optional[Dict[str, Any]] = None,
    increment_messages: bool = False
) -> bool:
    """
    Update an ACP session.
    
    Args:
        agent: The agent instance
        session_id: Session identifier
        state: New session state
        context: Context updates
        increment_messages: Whether to increment message count
        
    Returns:
        True if update successful, False if session not found
    """
    acp_sessions = agent.get_data(DATA_NAME_ACP_SESSIONS) or {}
    
    if session_id not in acp_sessions:
        return False
    
    session_data = acp_sessions[session_id]
    session = ACPSession(**session_data)
    
    if state:
        session.state = state
    
    if context:
        session.context.update(context)
    
    if increment_messages:
        session.message_count += 1
    
    session.last_activity = datetime.now(timezone.utc)
    
    acp_sessions[session_id] = session.__dict__
    agent.set_data(DATA_NAME_ACP_SESSIONS, acp_sessions)
    
    return True


def close_acp_session(agent: Agent, session_id: str) -> bool:
    """
    Close an ACP session.
    
    Args:
        agent: The agent instance
        session_id: Session identifier
        
    Returns:
        True if closed successfully, False if session not found
    """
    return update_acp_session(agent, session_id, state=SessionState.COMPLETED)


# A2A Task Management Functions

def create_a2a_task(
    agent: Agent,
    endpoint: str,
    task_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a new A2A task.
    
    Args:
        agent: The agent instance
        endpoint: Remote agent endpoint
        task_id: Optional custom task ID
        context: Initial task context
        
    Returns:
        Task ID
    """
    if not task_id:
        task_id = f"a2a_{int(time.time() * 1000)}_{agent.agent_name}"
    
    task = A2ATask(
        task_id=task_id,
        endpoint=endpoint,
        context=context or {}
    )
    
    a2a_tasks = agent.get_data(DATA_NAME_A2A_TASKS) or {}
    a2a_tasks[task_id] = task.__dict__
    agent.set_data(DATA_NAME_A2A_TASKS, a2a_tasks)
    
    return task_id


def get_a2a_task(agent: Agent, task_id: str) -> Optional[A2ATask]:
    """
    Get an A2A task by ID.
    
    Args:
        agent: The agent instance
        task_id: Task identifier
        
    Returns:
        A2ATask if found, None otherwise
    """
    a2a_tasks = agent.get_data(DATA_NAME_A2A_TASKS) or {}
    
    if task_id not in a2a_tasks:
        return None
    
    return A2ATask(**a2a_tasks[task_id])


def update_a2a_task(
    agent: Agent,
    task_id: str,
    state: Optional[TaskState] = None,
    context: Optional[Dict[str, Any]] = None,
    history_entry: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
) -> bool:
    """
    Update an A2A task.
    
    Args:
        agent: The agent instance
        task_id: Task identifier
        state: New task state
        context: Context updates
        history_entry: New history entry
        result: Task result (for completion)
        error: Error message (for failures)
        
    Returns:
        True if update successful, False if task not found
    """
    a2a_tasks = agent.get_data(DATA_NAME_A2A_TASKS) or {}
    
    if task_id not in a2a_tasks:
        return False
    
    task_data = a2a_tasks[task_id]
    task = A2ATask(**task_data)
    
    if state:
        task.state = state
    
    if context:
        task.context.update(context)
    
    if history_entry:
        task.history.append({
            **history_entry,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    if result:
        task.result = result
    
    if error:
        task.error = error
    
    task.last_update = datetime.now(timezone.utc)
    
    a2a_tasks[task_id] = task.__dict__
    agent.set_data(DATA_NAME_A2A_TASKS, a2a_tasks)
    
    return True


def complete_a2a_task(
    agent: Agent,
    task_id: str,
    result: Dict[str, Any]
) -> bool:
    """
    Mark an A2A task as completed.
    
    Args:
        agent: The agent instance
        task_id: Task identifier
        result: Task completion result
        
    Returns:
        True if completed successfully, False if task not found
    """
    return update_a2a_task(
        agent,
        task_id,
        state=TaskState.COMPLETED,
        result=result,
        history_entry={"action": "completed", "data": result}
    )


def fail_a2a_task(
    agent: Agent,
    task_id: str,
    error: str
) -> bool:
    """
    Mark an A2A task as failed.
    
    Args:
        agent: The agent instance
        task_id: Task identifier
        error: Error description
        
    Returns:
        True if failed successfully, False if task not found
    """
    return update_a2a_task(
        agent,
        task_id,
        state=TaskState.FAILED,
        error=error,
        history_entry={"action": "failed", "error": error}
    )


def get_session_statistics(agent: Agent) -> Dict[str, Any]:
    """
    Get comprehensive session statistics.
    
    Args:
        agent: The agent instance
        
    Returns:
        Dictionary with session statistics
    """
    return agent.get_data(DATA_NAME_SESSION_STATS) or {}


def get_active_sessions(agent: Agent) -> List[ACPSession]:
    """
    Get all active ACP sessions.
    
    Args:
        agent: The agent instance
        
    Returns:
        List of active ACPSession objects
    """
    acp_sessions = agent.get_data(DATA_NAME_ACP_SESSIONS) or {}
    return [
        ACPSession(**session_data)
        for session_data in acp_sessions.values()
        if ACPSession(**session_data).state == SessionState.ACTIVE
    ]


def get_active_tasks(agent: Agent) -> List[A2ATask]:
    """
    Get all active A2A tasks.
    
    Args:
        agent: The agent instance
        
    Returns:
        List of active A2ATask objects
    """
    a2a_tasks = agent.get_data(DATA_NAME_A2A_TASKS) or {}
    return [
        A2ATask(**task_data)
        for task_data in a2a_tasks.values()
        if A2ATask(**task_data).state in [TaskState.RUNNING, TaskState.WAITING_INPUT]
    ]