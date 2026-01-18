#!/usr/bin/env python3
"""
Parallel Worker Script

Runs a single agent task in complete isolation via subprocess.
Called by parallel_delegate.py - not meant to be run directly.
"""

import os
import sys

# Add project root to Python path (this script is in python/tools/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
import json
import traceback


async def run_agent(task_id: str, message: str, profile: str, agent_number: int,
                    coordinator_id: str, worktree_path: str, scratchpad_path: str) -> dict:
    """Run agent and return result as dict."""
    # Import everything fresh in this isolated process
    from agent import Agent, AgentContext, AgentContextType, UserMessage
    from initialize import initialize_agent

    try:
        # Create fresh config and context
        config = initialize_agent()
        config.profile = profile

        context = AgentContext(
            config=config,
            name=f"Parallel-{task_id}",
            type=AgentContextType.TASK,
        )

        agent = Agent(agent_number, config, context)

        # Store parallel coordination info
        agent.set_data("_parallel_task_id", task_id)
        agent.set_data("_parallel_coordinator_id", coordinator_id)
        agent.set_data("_parallel_worktree_path", worktree_path if worktree_path != "null" else None)
        agent.set_data("_parallel_scratchpad_path", scratchpad_path)

        # Run the agent
        agent.hist_add_user_message(UserMessage(message=message, attachments=[]))
        result = await agent.monologue()

        return {
            "task_id": task_id,
            "success": True,
            "result": result or "Task completed",
            "error": None,
        }

    except Exception as e:
        return {
            "task_id": task_id,
            "success": False,
            "result": "",
            "error": f"{str(e)}\n{traceback.format_exc()}",
        }


def main():
    """Entry point - read args from stdin as JSON, run agent, output result as JSON."""
    try:
        # Read input from stdin
        input_data = json.loads(sys.stdin.read())

        # Run the agent
        result = asyncio.run(run_agent(
            task_id=input_data["task_id"],
            message=input_data["message"],
            profile=input_data["profile"],
            agent_number=input_data["agent_number"],
            coordinator_id=input_data["coordinator_id"],
            worktree_path=input_data["worktree_path"],
            scratchpad_path=input_data["scratchpad_path"],
        ))

        # Output result as JSON to stdout
        print(json.dumps(result), flush=True)

    except Exception as e:
        # Output error as JSON
        print(json.dumps({
            "task_id": "unknown",
            "success": False,
            "result": "",
            "error": f"Worker error: {str(e)}\n{traceback.format_exc()}",
        }), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
