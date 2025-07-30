"""
Tool for creating subordinate agents using Agent Bridge with flow visualization.
This tool integrates with the gitgraph visualization to show real-time agent creation and management.
"""

import asyncio
import json
from typing import Dict, Any
from python.helpers.tool import Tool, Response
from python.helpers.agent_flow_bridge import agent_flow_bridge


class CreateSubordinateAgent(Tool):
    """
    Tool for creating and managing subordinate agents with real-time flow visualization.
    
    This tool:
    1. Creates subordinate agents using the Agent Bridge
    2. Automatically tracks them in the flow visualization
    3. Provides real-time updates in the gitgraph
    4. Manages agent lifecycle and cleanup
    """
    
    async def execute(self, **kwargs) -> Response:
        """
        Execute the subordinate agent creation.
        
        Args:
            action: Action to perform (create, send, complete)
            task_description: Description of the task for the subordinate
            agent_endpoint: Endpoint URL of the subordinate agent
            message: Message to send (for send/create actions)
            flow_id: Flow ID (for send/complete actions)
            timeout: Communication timeout (default: 30)
            success: Whether task completed successfully (for complete action)
        """
        action = kwargs.get("action", "create")
        
        try:
            if action == "create":
                return await self._create_subordinate(kwargs)
            elif action == "send":
                return await self._send_message(kwargs)
            elif action == "complete":
                return await self._complete_task(kwargs)
            elif action == "status":
                return await self._get_status(kwargs)
            else:
                return Response(
                    message=f"Unknown action: {action}. Available actions: create, send, complete, status",
                    data={"success": False, "error": f"Unknown action: {action}"}
                )
                
        except Exception as e:
            return Response(
                message=f"Error executing subordinate agent tool: {str(e)}",
                data={"success": False, "error": str(e)}
            )
    
    async def _create_subordinate(self, kwargs: Dict[str, Any]) -> Response:
        """Create a new subordinate agent."""
        task_description = kwargs.get("task_description")
        agent_endpoint = kwargs.get("agent_endpoint")
        initial_message = kwargs.get("message")
        timeout = float(kwargs.get("timeout", 30))
        
        if not task_description:
            return Response(
                message="Error: task_description is required for creating subordinate agent",
                data={"success": False, "error": "task_description is required"}
            )
        
        if not agent_endpoint:
            return Response(
                message="Error: agent_endpoint is required for creating subordinate agent",
                data={"success": False, "error": "agent_endpoint is required"}
            )
        
        # Get parent agent name from context
        parent_agent_name = getattr(self.agent, 'name', 'main_agent')
        
        print(f"🚀 Creating subordinate agent for task: {task_description}")
        print(f"📡 Agent endpoint: {agent_endpoint}")
        print(f"👤 Parent agent: {parent_agent_name}")
        
        # Create the subordinate agent
        result = await agent_flow_bridge.create_subordinate_agent(
            parent_agent_name=parent_agent_name,
            task_description=task_description,
            agent_endpoint=agent_endpoint,
            initial_message=initial_message,
            timeout=timeout
        )
        
        if result["success"]:
            message = f"""✅ Subordinate agent created successfully!

🆔 Flow ID: {result['flow_id']}
🤖 Agent ID: {result['agent_id']}
📡 Protocol: {result['protocol']}
🎯 Task: {task_description}

The agent is now visible in the real-time gitgraph visualization.
Use the flow_id to send messages or complete the task."""
            
            return Response(message=message, data=result)
        else:
            message = f"""❌ Failed to create subordinate agent:
{result['error']}

Please check the agent endpoint and try again."""
            
            return Response(message=message, data=result)
    
    async def _send_message(self, kwargs: Dict[str, Any]) -> Response:
        """Send a message to an existing subordinate agent."""
        flow_id = kwargs.get("flow_id")
        message = kwargs.get("message")
        timeout = float(kwargs.get("timeout", 30))
        
        if not flow_id:
            return Response(
                message="Error: flow_id is required for sending messages",
                data={"success": False, "error": "flow_id is required"}
            )
        
        if not message:
            return Response(
                message="Error: message is required for sending to subordinate",
                data={"success": False, "error": "message is required"}
            )
        
        print(f"📤 Sending message to subordinate in flow {flow_id}")
        print(f"💬 Message: {message}")
        
        # Send the message
        result = await agent_flow_bridge.send_message_to_subordinate(
            flow_id=flow_id,
            message=message,
            timeout=timeout
        )
        
        if result["success"]:
            response_data = result.get("response", {})
            agent_response = response_data.get("response", "No response content")
            
            message_text = f"""📨 Message sent successfully to subordinate agent!

🆔 Flow ID: {flow_id}
🤖 Agent ID: {result['agent_id']}
💬 Sent: {message}
📥 Response: {agent_response}

The interaction is now updated in the gitgraph visualization."""
            
            return Response(message=message_text, data=result)
        else:
            message_text = f"""❌ Failed to send message to subordinate agent:
{result['error']}

Flow ID: {flow_id}
Please check the agent status and try again."""
            
            return Response(message=message_text, data=result)
    
    async def _complete_task(self, kwargs: Dict[str, Any]) -> Response:
        """Complete a subordinate agent task."""
        flow_id = kwargs.get("flow_id")
        success = kwargs.get("success", True)
        final_message = kwargs.get("message")
        
        if not flow_id:
            return Response(
                message="Error: flow_id is required for completing tasks",
                data={"success": False, "error": "flow_id is required"}
            )
        
        print(f"🏁 Completing subordinate agent task in flow {flow_id}")
        print(f"✅ Success: {success}")
        
        # Complete the task
        result = await agent_flow_bridge.complete_subordinate_task(
            flow_id=flow_id,
            success=success,
            final_message=final_message
        )
        
        if result["success"]:
            status_emoji = "✅" if success else "❌"
            status_text = "completed successfully" if success else "failed"
            
            message_text = f"""{status_emoji} Subordinate agent task {status_text}!

🆔 Flow ID: {flow_id}
🤖 Agent ID: {result['agent_id']}
📊 Status: {result['status']}

The agent will be cleaned up and removed from the gitgraph visualization shortly."""
            
            return Response(message=message_text, data=result)
        else:
            message_text = f"""❌ Failed to complete subordinate agent task:
{result['error']}

Flow ID: {flow_id}"""
            
            return Response(message=message_text, data=result)
    
    async def _get_status(self, kwargs: Dict[str, Any]) -> Response:
        """Get status of subordinate agents."""
        flow_id = kwargs.get("flow_id")
        
        if flow_id:
            # Get specific subordinate status
            status = agent_flow_bridge.get_subordinate_status(flow_id)
            if status:
                message_text = f"""📊 Subordinate Agent Status:

🆔 Flow ID: {flow_id}
🤖 Agent ID: {status['agent_id']}
📡 Endpoint: {status['endpoint']}
👤 Parent: {status['parent_agent']}
📊 Status: {status['status']}
🕐 Created: {status['created_at']}
"""
                if 'last_communication' in status:
                    message_text += f"💬 Last Communication: {status['last_communication']}"
                
                return Response(message=message_text, data={"success": True, "status": status})
            else:
                return Response(
                    message=f"No subordinate agent found for flow ID: {flow_id}",
                    data={"success": False, "error": "Flow not found"}
                )
        else:
            # Get all active subordinates
            active_subordinates = agent_flow_bridge.get_active_subordinates()
            
            if active_subordinates:
                message_text = f"📊 Active Subordinate Agents ({len(active_subordinates)}):\n\n"
                
                for fid, status in active_subordinates.items():
                    message_text += f"""🆔 Flow: {fid}
🤖 Agent: {status['agent_id']} ({status['status']})
🎯 Parent: {status['parent_agent']}
📡 Endpoint: {status['endpoint']}
---
"""
                
                return Response(message=message_text, data={"success": True, "active_count": len(active_subordinates), "subordinates": active_subordinates})
            else:
                return Response(
                    message="📭 No active subordinate agents found.",
                    data={"success": True, "active_count": 0, "subordinates": {}}
                )


# Tool registration
def get_tool():
    return CreateSubordinateAgent(
        name="create_subordinate_agent",
        description="""Create and manage subordinate agents with real-time flow visualization.
        
Actions:
- create: Create a new subordinate agent
- send: Send a message to an existing subordinate
- complete: Mark a subordinate task as completed
- status: Get status of subordinate agents

Parameters:
- action: Action to perform (required)
- task_description: Task description (required for create)
- agent_endpoint: Agent endpoint URL (required for create)
- message: Message to send (for create/send/complete)
- flow_id: Flow ID (required for send/complete/status)
- timeout: Communication timeout in seconds (default: 30)
- success: Whether task completed successfully (for complete, default: true)

The tool automatically integrates with the gitgraph visualization to show:
- Real-time agent creation and progress
- Parallel agent execution
- Agent lifecycle management
- Automatic cleanup when tasks complete""",
        examples=[
            {
                "action": "create",
                "task_description": "Process data files",
                "agent_endpoint": "http://localhost:8001",
                "message": "Please process the uploaded CSV files"
            },
            {
                "action": "send",
                "flow_id": "flow_main_agent_subordinate_abc123",
                "message": "Status update request"
            },
            {
                "action": "complete",
                "flow_id": "flow_main_agent_subordinate_abc123",
                "success": True,
                "message": "Task completed successfully"
            }
        ]
    )
