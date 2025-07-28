#!/usr/bin/env python3
"""
Agent Zero ACP + A2A Integration Example
========================================

This example demonstrates how to use the new ACP (Agent Communication Protocol)
and A2A (Agent-to-Agent) integration features in Agent Zero.

Features demonstrated:
- Agent discovery and protocol detection
- Parallel execution of multiple tasks
- LLM bridge for local and remote calls
- Sub-agent management
- Session management

To run this example:
1. Ensure Agent Zero is properly installed with ACP/A2A dependencies
2. Set up any required API keys in your .env file
3. Run: python examples/acp_a2a_example.py
"""

import asyncio
import json
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python.tools.parallel_executor import ParallelExecutor, create_simple_operation, create_llm_operation
from python.tools.agent_bridge import AgentBridge, discover_agent
from python.tools.llm_bridge import LLMBridge, quick_llm_call
from python.helpers.concurrency_limiter import ConcurrencyLimiter
from python.extensions.message_loop_start._35_sub_agent_manager import register_sub_agent, broadcast_to_sub_agents
from python.extensions.monologue_start._40_llm_session_manager import create_acp_session, create_a2a_task


class MockAgent:
    """Mock agent for demonstration purposes."""
    
    def __init__(self, name: str = "ExampleAgent"):
        self.agent_name = name
        self.data = {}
        self.context = MockContext()
        
    def get_data(self, key: str):
        return self.data.get(key)
    
    def set_data(self, key: str, value):
        self.data[key] = value
    
    def get_chat_model(self):
        # Return a mock chat model for demonstration
        return MockChatModel()


class MockContext:
    """Mock context for demonstration."""
    
    def __init__(self):
        self.log = MockLog()


class MockLog:
    """Mock log for demonstration."""
    
    def log(self, **kwargs):
        return MockLogItem()


class MockLogItem:
    """Mock log item for demonstration."""
    
    def update(self, **kwargs):
        pass


class MockChatModel:
    """Mock chat model for demonstration."""
    
    def __init__(self):
        self.model_name = "gpt-3.5-turbo"
        self.provider = "openai"
    
    async def unified_call(self, **kwargs):
        # Simulate LLM response
        await asyncio.sleep(0.1)
        return "This is a mock LLM response.", "Mock reasoning"


async def demonstrate_concurrency_limiter():
    """Demonstrate the ConcurrencyLimiter functionality."""
    print("\n🔄 Demonstrating ConcurrencyLimiter")
    print("=" * 50)
    
    async def sample_task(task_id: int, delay: float = 0.2):
        async with ConcurrencyLimiter.guard("demo", 2):
            print(f"  Task {task_id} started")
            await asyncio.sleep(delay)
            print(f"  Task {task_id} completed")
            return f"Result from task {task_id}"
    
    # Run 4 tasks with concurrency limit of 2
    print("Running 4 tasks with max concurrency of 2...")
    start_time = asyncio.get_event_loop().time()
    
    tasks = [sample_task(i) for i in range(1, 5)]
    results = await asyncio.gather(*tasks)
    
    end_time = asyncio.get_event_loop().time()
    print(f"✅ Completed in {end_time - start_time:.2f} seconds")
    print(f"📊 Results: {len(results)} tasks completed")
    
    # Clean up
    await ConcurrencyLimiter.reset_all()


async def demonstrate_parallel_executor():
    """Demonstrate the ParallelExecutor tool."""
    print("\n⚡ Demonstrating ParallelExecutor")
    print("=" * 50)
    
    mock_agent = MockAgent()
    
    # Create some sample operations
    operations = [
        create_simple_operation(f"Process batch {i}", 0.1)
        for i in range(1, 6)
    ]
    
    executor = ParallelExecutor(
        agent=mock_agent,
        name="parallel_executor",
        method=None,
        args={
            "operations": json.dumps(operations),
            "max_concurrency": "3",
            "timeout": "10"
        },
        message="",
        loop_data=None
    )
    
    print("Executing 5 operations in parallel (max concurrency: 3)...")
    start_time = asyncio.get_event_loop().time()
    
    response = await executor.execute()
    
    end_time = asyncio.get_event_loop().time()
    print(f"✅ Completed in {end_time - start_time:.2f} seconds")
    
    # Parse and display results
    try:
        result = json.loads(response.message)
        print(f"📊 Results: {result['successful']}/{result['total_operations']} successful")
        if result['failed'] > 0:
            print(f"❌ Failed operations: {result['failed']}")
    except json.JSONDecodeError:
        print(f"📄 Response: {response.message[:100]}...")


async def demonstrate_agent_bridge():
    """Demonstrate the AgentBridge tool."""
    print("\n🌉 Demonstrating AgentBridge")
    print("=" * 50)
    
    mock_agent = MockAgent()
    
    # Test with a fake endpoint (will fail gracefully)
    bridge = AgentBridge(
        agent=mock_agent,
        name="agent_bridge",
        method=None,
        args={
            "endpoint": "https://fake-agent.example.com",
            "action": "discover",
            "timeout": "5"
        },
        message="",
        loop_data=None
    )
    
    print("Attempting to discover agent at fake endpoint...")
    response = await bridge.execute()
    
    try:
        result = json.loads(response.message)
        if result.get("protocol") == "unknown":
            print("❌ No agent found (expected for demo)")
            print(f"🔍 Attempted protocols: {result.get('attempted', [])}")
        else:
            print(f"✅ Discovered {result['protocol']} agent")
            print(f"🆔 Agent ID: {result.get('agent_id', 'unknown')}")
    except json.JSONDecodeError:
        print(f"📄 Response: {response.message[:100]}...")


async def demonstrate_llm_bridge():
    """Demonstrate the LLMBridge tool."""
    print("\n🧠 Demonstrating LLMBridge")
    print("=" * 50)
    
    mock_agent = MockAgent()
    
    bridge = LLMBridge(
        agent=mock_agent,
        name="llm_bridge",
        method=None,
        args={
            "prompt": "What is the capital of France?",
            "system_message": "You are a helpful geography assistant.",
            "temperature": "0.7",
            "format": "detailed"
        },
        message="",
        loop_data=None
    )
    
    print("Making a local LLM call via bridge...")
    response = await bridge.execute()
    
    try:
        result = json.loads(response.message)
        print(f"✅ Response: {result['response']}")
        print(f"🤖 Model: {result['model_used']}")
        print(f"⚡ Duration: {result['duration']}s")
        if result.get('reasoning'):
            print(f"🧠 Reasoning: {result['reasoning']}")
    except json.JSONDecodeError:
        print(f"📄 Response: {response.message}")


async def demonstrate_sub_agent_management():
    """Demonstrate sub-agent management."""
    print("\n👥 Demonstrating Sub-Agent Management")
    print("=" * 50)
    
    mock_agent = MockAgent()
    
    # Register some sub-agents
    agents_to_register = [
        ("research-agent", "https://research.example.com"),
        ("analysis-agent", "https://analysis.example.com"),
        ("creative-agent", "https://creative.example.com")
    ]
    
    print("Registering sub-agents...")
    for agent_id, endpoint in agents_to_register:
        success = register_sub_agent(mock_agent, agent_id, endpoint)
        status = "✅" if success else "❌"
        print(f"  {status} {agent_id}: {endpoint}")
    
    # Try to register duplicate (should fail)
    duplicate_success = register_sub_agent(mock_agent, "research-agent", "https://duplicate.com")
    print(f"  ❌ Duplicate registration: {'succeeded' if duplicate_success else 'failed (expected)'}")
    
    print(f"\n📊 Total registered agents: {len(mock_agent.get_data('sub_agents_registry') or {})}")


async def demonstrate_session_management():
    """Demonstrate session management."""
    print("\n📊 Demonstrating Session Management")
    print("=" * 50)
    
    mock_agent = MockAgent()
    
    # Create ACP session
    acp_session_id = create_acp_session(
        mock_agent,
        "https://acp-agent.example.com",
        timeout=600.0,
        context={"user_id": "demo_user", "task": "research"}
    )
    print(f"✅ Created ACP session: {acp_session_id}")
    
    # Create A2A task
    a2a_task_id = create_a2a_task(
        mock_agent,
        "https://a2a-agent.example.com",
        context={"priority": "high", "category": "analysis"}
    )
    print(f"✅ Created A2A task: {a2a_task_id}")
    
    # Display session statistics
    acp_sessions = mock_agent.get_data("acp_sessions") or {}
    a2a_tasks = mock_agent.get_data("a2a_tasks") or {}
    
    print(f"📊 Active ACP sessions: {len(acp_sessions)}")
    print(f"📊 Active A2A tasks: {len(a2a_tasks)}")


async def demonstrate_performance_comparison():
    """Demonstrate performance benefits of parallel execution.""" 
    print("\n🏃 Demonstrating Performance Benefits")
    print("=" * 50)
    
    mock_agent = MockAgent()
    
    # Create operations that simulate real work
    num_operations = 6
    operation_delay = 0.1
    
    print(f"Comparing serial vs parallel execution of {num_operations} operations...")
    print(f"Each operation takes ~{operation_delay}s")
    
    # Serial execution simulation
    print("\n🐌 Serial execution:")
    start_time = asyncio.get_event_loop().time()
    
    for i in range(num_operations):
        await asyncio.sleep(operation_delay)
    
    serial_time = asyncio.get_event_loop().time() - start_time
    print(f"  Time: {serial_time:.2f}s")
    
    # Parallel execution using ParallelExecutor
    print("\n⚡ Parallel execution (concurrency=3):")
    operations = [
        create_simple_operation(f"task{i}", operation_delay)
        for i in range(num_operations)
    ]
    
    executor = ParallelExecutor(
        agent=mock_agent,
        name="parallel_executor",
        method=None,
        args={
            "operations": json.dumps(operations),
            "max_concurrency": "3"
        },
        message="",
        loop_data=None
    )
    
    start_time = asyncio.get_event_loop().time()
    response = await executor.execute()
    parallel_time = asyncio.get_event_loop().time() - start_time
    
    print(f"  Time: {parallel_time:.2f}s")
    
    # Calculate speedup
    speedup = serial_time / parallel_time if parallel_time > 0 else 0
    print(f"\n🚀 Speedup: {speedup:.1f}x faster")
    print(f"📈 Time saved: {serial_time - parallel_time:.2f}s ({((serial_time - parallel_time) / serial_time * 100):.1f}%)")


async def main():
    """Run the complete ACP + A2A integration demonstration."""
    print("🤖 Agent Zero ACP + A2A Integration Demo")
    print("=" * 60)
    
    try:
        # Run all demonstrations
        await demonstrate_concurrency_limiter()
        await demonstrate_parallel_executor()
        await demonstrate_agent_bridge()
        await demonstrate_llm_bridge()
        await demonstrate_sub_agent_management()
        await demonstrate_session_management()
        await demonstrate_performance_comparison()
        
        print("\n" + "=" * 60)
        print("🎉 Demo completed successfully!")
        print("\nKey features demonstrated:")
        print("  ✅ Concurrency limiting and control")
        print("  ✅ Parallel task execution")
        print("  ✅ Agent discovery and communication")
        print("  ✅ LLM bridge for local/remote calls") 
        print("  ✅ Sub-agent management")
        print("  ✅ Session and task lifecycle management")
        print("  ✅ Performance optimization")
        
        print("\nNext steps:")
        print("  • Configure real agent endpoints in conf/model_providers.yaml")
        print("  • Set up API keys in your .env file")
        print("  • Use these tools in your Agent Zero workflows")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run the demonstration
    asyncio.run(main())