"""
Async Task Coordinator for parallel agent execution in the mesh.
Handles multiple agent tasks concurrently with proper timeout management.
"""

import asyncio
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor
from agent import AgentContext, UserMessage, AgentContextType

class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"

class AsyncTaskCoordinator:
    def __init__(self, max_workers: int = 3, task_timeout: int = 35):
        """
        Initialize the coordinator.
        
        Args:
            max_workers: Maximum number of concurrent agent tasks
            task_timeout: Timeout in seconds for each task (default 35 seconds)
        """
        self.max_workers = max_workers
        self.task_timeout = task_timeout
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
    async def submit_task(self, goal: str, context_id: Optional[str] = None) -> str:
        """
        Submit a task for async execution.
        
        Args:
            goal: The task goal/prompt
            context_id: Optional specific context ID to use
            
        Returns:
            task_id: Unique identifier for the task
        """
        task_id = str(uuid.uuid4())
        
        # Create task record
        task = {
            "task_id": task_id,
            "goal": goal,
            "context_id": context_id,
            "status": TaskStatus.PENDING,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "progress": []
        }
        
        self.tasks[task_id] = task
        
        # Start async execution and track the task
        async_task = asyncio.create_task(self._execute_task(task_id))
        self.running_tasks[task_id] = async_task
        
        # Add completion callback to clean up tracking
        def task_done_callback(finished_task):
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
        
        async_task.add_done_callback(task_done_callback)
        
        return task_id
    
    async def submit_batch(self, goals: List[str]) -> List[str]:
        """
        Submit multiple tasks for parallel execution.
        
        Args:
            goals: List of task goals
            
        Returns:
            List of task IDs
        """
        task_ids = []
        for goal in goals:
            task_id = await self.submit_task(goal)
            task_ids.append(task_id)
        return task_ids
    
    async def _execute_task(self, task_id: str):
        """Execute a single task asynchronously."""
        task = self.tasks.get(task_id)
        if not task:
            return
        
        future = None
        try:
            # Update status
            task["status"] = TaskStatus.RUNNING
            task["started_at"] = datetime.now().isoformat()
            self._add_progress(task_id, "Task execution started")
            
            # Run in executor to avoid blocking with reduced timeout
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(
                self.executor,
                self._run_agent_task,
                task["goal"],
                task["context_id"]
            )
            
            # Wait with timeout - use the reduced timeout
            result = await asyncio.wait_for(future, timeout=self.task_timeout)
            
            # Update success status
            task["status"] = TaskStatus.COMPLETED
            task["result"] = result
            task["completed_at"] = datetime.now().isoformat()
            self._add_progress(task_id, "Task completed successfully")
            
        except asyncio.CancelledError:
            # Task was cancelled - clean up gracefully
            task["status"] = TaskStatus.FAILED
            task["error"] = "Task was cancelled"
            task["completed_at"] = datetime.now().isoformat()
            self._add_progress(task_id, "Task cancelled")
            if future and not future.done():
                future.cancel()
            
        except asyncio.TimeoutError:
            task["status"] = TaskStatus.TIMEOUT
            task["error"] = f"Task timeout after {self.task_timeout} seconds"
            task["completed_at"] = datetime.now().isoformat()
            self._add_progress(task_id, f"Task timed out after {self.task_timeout}s")
            if future and not future.done():
                future.cancel()
            print(f"[AsyncCoordinator] Task {task_id} timed out at coordinator level")
            
        except Exception as e:
            task["status"] = TaskStatus.FAILED
            task["error"] = str(e)
            task["completed_at"] = datetime.now().isoformat()
            self._add_progress(task_id, f"Task failed: {str(e)}")
            print(f"[AsyncCoordinator] Task {task_id} failed: {str(e)}")
            if future and not future.done():
                future.cancel()
    
    def _run_agent_task(self, goal: str, context_id: Optional[str] = None) -> str:
        """Run agent task in thread (blocking)."""
        context = None
        temp_context = False
        try:
            # Get or create context
            if context_id:
                contexts = [c for c in AgentContext.all() if c.id == context_id]
                context = contexts[0] if contexts else None
            else:
                contexts = AgentContext.all()
                context = contexts[0] if contexts else None
                
            # If no context exists, create a temporary one
            if not context:
                print(f"[AsyncCoordinator] No contexts available, creating temporary context")
                from initialize import initialize_agent
                cfg = initialize_agent()
                context = AgentContext(cfg, type=AgentContextType.BACKGROUND)
                temp_context = True
                print(f"[AsyncCoordinator] Created temporary context {context.id}")
            
            # Execute task
            user_msg = UserMessage(message=goal, attachments=[])
            task = context.communicate(user_msg)
            
            print(f"[AsyncCoordinator] Starting task execution for: {goal[:100]}...")
            
            try:
                # Use a shorter timeout and simpler approach
                result = task.result_sync(timeout=30)  # Reduced to 30 seconds
                print(f"[AsyncCoordinator] Task completed successfully")
                return str(result) if result else "Task completed"
            except TimeoutError:
                print(f"[AsyncCoordinator] Task timed out after 30s")
                # Kill the task to prevent hanging
                if task and hasattr(task, 'kill'):
                    task.kill()
                raise TimeoutError("Task execution timed out after 30 seconds")
            except Exception as e:
                print(f"[AsyncCoordinator] Task execution error: {e}")
                # Kill the task on error
                if task and hasattr(task, 'kill'):
                    task.kill()
                raise
            
        except Exception as e:
            # Better error reporting
            error_msg = f"Agent task failed: {type(e).__name__}: {str(e)}"
            print(f"[AsyncCoordinator] {error_msg}")
            raise Exception(error_msg) from e
        finally:
            # Clean up temporary context
            if temp_context and context:
                try:
                    context.reset()
                    AgentContext.remove(context.id)
                    from python.helpers.persist_chat import remove_chat
                    remove_chat(context.id)
                    print(f"[AsyncCoordinator] Cleaned up temporary context {context.id}")
                except Exception as e:
                    print(f"[AsyncCoordinator] Error cleaning up context: {e}")
    
    def _add_progress(self, task_id: str, message: str):
        """Add progress update to task."""
        if task_id in self.tasks:
            self.tasks[task_id]["progress"].append({
                "timestamp": datetime.now().isoformat(),
                "message": message
            })
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a task."""
        return self.tasks.get(task_id)
    
    async def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get all tasks."""
        return self.tasks.copy()
    
    async def wait_for_task(self, task_id: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Wait for a task to complete.
        
        Args:
            task_id: Task ID to wait for
            timeout: Optional timeout in seconds
            
        Returns:
            Final task status
        """
        start_time = time.time()
        
        while True:
            task = self.tasks.get(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            # Check if task is done
            if task["status"] in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.TIMEOUT]:
                return task
            
            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Timeout waiting for task {task_id}")
            
            # Wait a bit before checking again
            await asyncio.sleep(0.5)
    
    async def wait_for_batch(self, task_ids: List[str], timeout: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Wait for multiple tasks to complete.
        
        Args:
            task_ids: List of task IDs to wait for
            timeout: Optional timeout for all tasks
            
        Returns:
            List of final task statuses
        """
        # Create wait tasks
        wait_tasks = [
            self.wait_for_task(task_id, timeout)
            for task_id in task_ids
        ]
        
        # Wait for all tasks
        results = await asyncio.gather(*wait_tasks, return_exceptions=True)
        
        # Convert exceptions to error results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Create error result
                task_id = task_ids[i]
                error_result = {
                    "task_id": task_id,
                    "status": TaskStatus.FAILED,
                    "error": str(result)
                }
                final_results.append(error_result)
            else:
                final_results.append(result)
        
        return final_results
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id in self.running_tasks:
            task = self.running_tasks[task_id]
            if not task.done():
                task.cancel()
                # Update task status
                if task_id in self.tasks:
                    self.tasks[task_id]["status"] = TaskStatus.FAILED
                    self.tasks[task_id]["error"] = "Task cancelled by user"
                    self.tasks[task_id]["completed_at"] = datetime.now().isoformat()
                return True
        return False
    
    async def shutdown(self):
        """Shutdown the coordinator and cancel all tasks."""
        # Cancel all running tasks
        for task_id, task in list(self.running_tasks.items()):
            if not task.done():
                task.cancel()
        
        # Wait for all tasks to complete or cancel
        if self.running_tasks:
            await asyncio.gather(*self.running_tasks.values(), return_exceptions=True)
        
        # Shutdown executor
        self.executor.shutdown(wait=True)

# Global coordinator instance
_coordinator = None

def get_coordinator() -> AsyncTaskCoordinator:
    """Get or create the global coordinator instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = AsyncTaskCoordinator()
    return _coordinator