#!/usr/bin/env python3
"""
Advanced example showing multi-agent workflow with detailed Opik tracing
"""

import os
import sys
import asyncio

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import ModelProvider
from agent import ModelConfig, Agent, AgentConfig
from python.helpers.opik_init import initialize_opik_integration
from python.helpers.opik_client import get_opik_tracker

async def research_task(agent: Agent, topic: str) -> str:
    """Research task that will be traced"""
    tracker = get_opik_tracker()
    
    # Start a custom trace for this research task
    trace_id = None
    if tracker:
        trace_id = tracker.start_trace(
            name=f"Research Task: {topic}",
            input_data={"topic": topic, "agent": agent.agent_name},
            metadata={"task_type": "research", "complexity": "high"}
        )
    
    try:
        # Perform research
        research_prompt = f"""
        Please research the topic: {topic}
        
        Provide:
        1. Key facts and information
        2. Recent developments
        3. Important considerations
        4. Reliable sources
        
        Be thorough and accurate.
        """
        
        result = await agent.message.loop(research_prompt)
        
        # End the trace successfully
        if tracker and trace_id:
            tracker.end_trace(
                trace_id=trace_id,
                output_data={"research_result": result, "status": "completed"},
                success=True
            )
        
        return result
        
    except Exception as e:
        # End the trace with error
        if tracker and trace_id:
            tracker.end_trace(
                trace_id=trace_id,
                output_data={"error": str(e), "status": "failed"},
                success=False,
                error=str(e)
            )
        raise

async def analysis_task(agent: Agent, research_data: str, focus: str) -> str:
    """Analysis task that will be traced"""
    tracker = get_opik_tracker()
    
    # Start a custom trace for analysis
    trace_id = None
    if tracker:
        trace_id = tracker.start_trace(
            name=f"Analysis Task: {focus}",
            input_data={"research_data": research_data[:500] + "...", "focus": focus},
            metadata={"task_type": "analysis", "data_length": len(research_data)}
        )
    
    try:
        analysis_prompt = f"""
        Based on this research data:
        {research_data}
        
        Please provide a detailed analysis focusing on: {focus}
        
        Include:
        1. Key insights
        2. Patterns and trends
        3. Implications
        4. Recommendations
        """
        
        result = await agent.message_loop(analysis_prompt)
        
        if tracker and trace_id:
            tracker.end_trace(
                trace_id=trace_id,
                output_data={"analysis_result": result, "status": "completed"},
                success=True
            )
        
        return result
        
    except Exception as e:
        if tracker and trace_id:
            tracker.end_trace(
                trace_id=trace_id,
                output_data={"error": str(e), "status": "failed"},
                success=False,
                error=str(e)
            )
        raise

async def main():
    """Advanced multi-agent workflow with Opik tracing"""
    
    print("🚀 Starting Advanced Agent Zero + Opik Workflow")
    
    # Initialize Opik integration
    opik_tracker = initialize_opik_integration()
    
    if not opik_tracker or not opik_tracker.is_enabled():
        print("❌ Opik integration required for this example")
        return
    
    print("✅ Opik integration active")
    
    # Create multiple agents with different roles
    base_config = AgentConfig(
        chat_model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4"),
        utility_model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-3.5-turbo"),
        embeddings_model=ModelConfig(provider=ModelProvider.OPENAI, name="text-embedding-3-small")
    )
    
    # Research agent
    research_agent = Agent(1, base_config)
    research_agent.agent_name = "Research Specialist"
    
    # Analysis agent  
    analysis_agent = Agent(2, base_config)
    analysis_agent.agent_name = "Data Analyst"
    
    # Start main workflow trace
    main_trace_id = opik_tracker.start_trace(
        name="Multi-Agent Research & Analysis Workflow",
        input_data={"workflow": "research_and_analysis", "agents": 2},
        metadata={"workflow_type": "multi_agent", "complexity": "high"}
    )
    
    try:
        # Step 1: Research
        print("\n📚 Step 1: Conducting research...")
        research_topic = "Artificial Intelligence in Healthcare 2024"
        research_result = await research_task(research_agent, research_topic)
        print(f"✅ Research completed: {len(research_result)} characters")
        
        # Step 2: Analysis
        print("\n🔍 Step 2: Analyzing research data...")
        analysis_focus = "practical applications and ethical considerations"
        analysis_result = await analysis_task(analysis_agent, research_result, analysis_focus)
        print(f"✅ Analysis completed: {len(analysis_result)} characters")
        
        # Complete main workflow
        final_output = {
            "research_summary": research_result[:200] + "...",
            "analysis_summary": analysis_result[:200] + "...",
            "total_agents_used": 2,
            "workflow_status": "completed"
        }
        
        opik_tracker.end_trace(
            trace_id=main_trace_id,
            output_data=final_output,
            success=True
        )
        
        print(f"\n🎯 Final Analysis Preview:")
        print(f"{analysis_result[:300]}...")
        
    except Exception as e:
        print(f"\n❌ Workflow failed: {e}")
        opik_tracker.end_trace(
            trace_id=main_trace_id,
            output_data={"error": str(e), "status": "failed"},
            success=False,
            error=str(e)
        )
    
    finally:
        # Flush all traces
        opik_tracker.flush()
        print("\n✅ All traces sent to Opik dashboard")
        print("🎉 Check your detailed workflow traces at http://localhost:5173")

if __name__ == "__main__":
    asyncio.run(main())
