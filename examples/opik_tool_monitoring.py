#!/usr/bin/env python3
"""
Example showing tool usage monitoring with Opik
"""

import os
import sys
import asyncio
import time

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import ModelProvider
from agent import ModelConfig, Agent, AgentConfig
from python.helpers.opik_init import initialize_opik_integration
from python.helpers.opik_client import get_opik_tracker

async def simulate_tool_usage():
    """Simulate various tool executions for monitoring"""
    
    tracker = get_opik_tracker()
    if not tracker:
        print("❌ Opik tracker not available")
        return
    
    print("🔧 Simulating tool executions...")
    
    # Simulate different types of tool usage
    tools_to_simulate = [
        {
            "name": "web_search",
            "args": {"query": "latest AI developments", "max_results": 10},
            "duration": 2.3,
            "success": True,
            "result": "Found 10 relevant articles about AI developments"
        },
        {
            "name": "file_reader", 
            "args": {"path": "/data/research.txt", "encoding": "utf-8"},
            "duration": 0.5,
            "success": True,
            "result": "Successfully read 1,234 lines from research.txt"
        },
        {
            "name": "code_executor",
            "args": {"language": "python", "code": "print('Hello World')"},
            "duration": 1.2,
            "success": True,
            "result": "Hello World\nExecution completed successfully"
        },
        {
            "name": "api_caller",
            "args": {"endpoint": "https://api.example.com/data", "method": "GET"},
            "duration": 3.1,
            "success": False,
            "result": "Connection timeout",
            "error": "Request timeout after 30 seconds"
        },
        {
            "name": "data_processor",
            "args": {"input_file": "data.csv", "operation": "aggregate"},
            "duration": 4.7,
            "success": True,
            "result": "Processed 50,000 records, generated summary statistics"
        }
    ]
    
    for i, tool in enumerate(tools_to_simulate, 1):
        print(f"  🛠️ Executing tool {i}/5: {tool['name']}")
        
        # Log tool execution
        tracker.log_tool_execution(
            tool_name=tool["name"],
            args=tool["args"],
            result=tool["result"],
            success=tool["success"],
            duration=tool["duration"],
            agent_name="Tool Monitor Agent",
            error=tool.get("error")
        )
        
        # Small delay to simulate real execution
        await asyncio.sleep(0.5)
    
    print("✅ All tool executions logged to Opik")

async def simulate_llm_calls():
    """Simulate LLM calls for monitoring"""
    
    tracker = get_opik_tracker()
    if not tracker:
        return
    
    print("🤖 Simulating LLM calls...")
    
    llm_calls = [
        {
            "model": "gpt-4",
            "provider": "openai",
            "input": "Explain quantum computing in simple terms",
            "output": "Quantum computing uses quantum mechanics principles to process information in ways that classical computers cannot...",
            "tokens": 156,
            "duration": 2.8
        },
        {
            "model": "gpt-3.5-turbo",
            "provider": "openai", 
            "input": "Summarize this text: [long text content]",
            "output": "The text discusses the importance of renewable energy sources and their impact on climate change...",
            "tokens": 89,
            "duration": 1.4
        },
        {
            "model": "claude-3-sonnet",
            "provider": "anthropic",
            "input": "Write a Python function to calculate fibonacci numbers",
            "output": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
            "tokens": 67,
            "duration": 1.9
        }
    ]
    
    for i, call in enumerate(llm_calls, 1):
        print(f"  🧠 LLM call {i}/3: {call['model']}")
        
        tracker.log_llm_call(
            model_name=call["model"],
            provider=call["provider"],
            input_text=call["input"],
            output_text=call["output"],
            tokens_used=call["tokens"],
            duration=call["duration"],
            agent_name="LLM Monitor Agent"
        )
        
        await asyncio.sleep(0.3)
    
    print("✅ All LLM calls logged to Opik")

async def main():
    """Tool and LLM monitoring example"""
    
    print("🚀 Starting Tool & LLM Monitoring with Opik")
    
    # Initialize Opik
    opik_tracker = initialize_opik_integration()
    
    if not opik_tracker or not opik_tracker.is_enabled():
        print("❌ Opik integration required for this example")
        return
    
    print("✅ Opik monitoring active")
    
    # Start main monitoring trace
    main_trace_id = opik_tracker.start_trace(
        name="Agent Zero - Tool & LLM Monitoring Session",
        input_data={"session_type": "monitoring", "components": ["tools", "llm"]},
        metadata={"monitoring_session": True, "timestamp": time.time()}
    )
    
    try:
        # Monitor tool usage
        await simulate_tool_usage()
        
        # Monitor LLM calls
        await simulate_llm_calls()
        
        # Log some agent conversations
        print("💬 Logging agent conversations...")
        
        conversations = [
            {
                "user": "How can I improve my Python coding skills?",
                "agent": "Here are some effective ways to improve your Python skills: 1) Practice coding daily, 2) Work on real projects, 3) Read other people's code, 4) Contribute to open source...",
                "success": True
            },
            {
                "user": "What's the weather like today?",
                "agent": "I don't have access to real-time weather data. You can check weather websites or apps for current conditions in your area.",
                "success": True
            }
        ]
        
        for conv in conversations:
            opik_tracker.log_agent_conversation(
                agent_name="Assistant Agent",
                user_message=conv["user"],
                agent_response=conv["agent"],
                success=conv["success"]
            )
        
        # Complete monitoring session
        session_summary = {
            "tools_monitored": 5,
            "llm_calls_monitored": 3,
            "conversations_logged": 2,
            "session_duration": "~30 seconds",
            "status": "completed"
        }
        
        opik_tracker.end_trace(
            trace_id=main_trace_id or "",
            output_data=session_summary,
            success=True
        )
        
        print("\n📊 Monitoring Session Summary:")
        print(f"  • Tools monitored: {session_summary['tools_monitored']}")
        print(f"  • LLM calls tracked: {session_summary['llm_calls_monitored']}")
        print(f"  • Conversations logged: {session_summary['conversations_logged']}")
        
    except Exception as e:
        print(f"❌ Monitoring failed: {e}")
        opik_tracker.end_trace(
            trace_id=main_trace_id or "",
            output_data={"error": str(e)},
            success=False,
            error=str(e)
        )
    
    finally:
        # Flush all monitoring data
        opik_tracker.flush()
        print("\n✅ All monitoring data sent to Opik")
        print("📈 View detailed analytics at http://localhost:5173")

if __name__ == "__main__":
    asyncio.run(main())
