from agent import AgentContext, UserMessage
from python.helpers.api import ApiHandler, Request, Response
from python.tools.agent_bridge import AgentBridge

from python.helpers import files
import os
from werkzeug.utils import secure_filename
from python.helpers.defer import DeferredTask
from python.helpers.print_style import PrintStyle


class Message(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        task, context = await self.communicate(input=input, request=request)
        return await self.respond(task, context)

    async def respond(self, task: DeferredTask, context: AgentContext):
        result = await task.result()  # type: ignore
        return {
            "message": result,
            "context": context.id,
        }

    async def communicate(self, input: dict, request: Request):
        # Handle both JSON and multipart/form-data
        if request.content_type.startswith("multipart/form-data"):
            text = request.form.get("text", "")
            ctxid = request.form.get("context", "")
            message_id = request.form.get("message_id", None)
            attachments = request.files.getlist("attachments")
            attachment_paths = []

            upload_folder_int = "/a0/tmp/uploads"
            upload_folder_ext = files.get_abs_path("tmp/uploads") # for development environment

            if attachments:
                os.makedirs(upload_folder_ext, exist_ok=True)
                for attachment in attachments:
                    if attachment.filename is None:
                        continue
                    filename = secure_filename(attachment.filename)
                    save_path = files.get_abs_path(upload_folder_ext, filename)
                    attachment.save(save_path)
                    attachment_paths.append(os.path.join(upload_folder_int, filename))
        else:
            # Handle JSON request as before
            input_data = request.get_json()
            text = input_data.get("text", "")
            ctxid = input_data.get("context", "")
            message_id = input_data.get("message_id", None)
            attachment_paths = []

        # Now process the message
        message = text

        # Obtain agent context
        context = self.get_context(ctxid)
        
        # Check if agent routing is enabled
        if context.get_agent().get_data("agent_routing_enabled"):
            return await self._route_to_subordinate_agent(context, message, attachment_paths, message_id)

        # Store attachments in agent data
        # context.agent0.set_data("attachments", attachment_paths)

        # Prepare attachment filenames for logging
        attachment_filenames = (
            [os.path.basename(path) for path in attachment_paths]
            if attachment_paths
            else []
        )

        # Print to console and log
        PrintStyle(
            background_color="#6C3483", font_color="white", bold=True, padding=True
        ).print(f"User message:")
        PrintStyle(font_color="white", padding=False).print(f"> {message}")
        if attachment_filenames:
            PrintStyle(font_color="white", padding=False).print("Attachments:")
            for filename in attachment_filenames:
                PrintStyle(font_color="white", padding=False).print(f"- {filename}")

        # Log the message with message_id and attachments
        context.log.log(
            type="user",
            heading="User message",
            content=message,
            kvps={"attachments": attachment_filenames},
            id=message_id,
        )

        return context.communicate(UserMessage(message, attachment_paths)), context
    
    async def _route_to_subordinate_agent(self, context: AgentContext, message: str, attachment_paths: list, message_id: str):
        """Route message to the selected subordinate agent using real ACP/A2A protocols."""
        endpoint = context.get_agent().get_data("subordinate_agent_endpoint")
        agent_info = context.get_agent().get_data("selected_agent_id")
        protocol = context.get_agent().get_data("subordinate_agent_protocol", "unknown")
        
        if not endpoint:
            # Fallback to main agent if routing is broken
            context.get_agent().set_data("agent_routing_enabled", False)
            return context.communicate(UserMessage(message, attachment_paths)), context
        
        # Log routing attempt
        PrintStyle(
            background_color="#8E44AD", font_color="white", bold=True, padding=True
        ).print(f"Routing message via {protocol} protocol to: {agent_info}")
        PrintStyle(font_color="white", padding=False).print(f"> {message}")
        
        try:
            # Create agent bridge tool with the appropriate action for the protocol
            bridge_action = "send"  # Both ACP and A2A support message sending
            
            bridge = AgentBridge(
                agent=context.agent,
                name="agent_bridge", 
                method=None,
                args={
                    "endpoint": endpoint,
                    "action": bridge_action,
                    "message": message,
                    "sender": "agent-zero",
                    "context": context.id,
                    "timeout": "30",
                    # Pass additional context info for better continuity
                    "session_data": {
                        "user_session": context.id,
                        "routing_from": "main_agent",
                        "attachment_paths": attachment_paths
                    }
                },
                message="",
                loop_data=None
            )
            
            # Execute the bridge call
            response = await bridge.execute()
            
            # Parse the response JSON to extract the actual message
            import json
            try:
                response_data = json.loads(response.message)
                
                # Handle different protocol response formats
                if protocol == "ACP":
                    actual_message = response_data.get("output", response.message)
                elif protocol == "A2A":
                    if "result" in response_data:
                        result = response_data["result"]
                        actual_message = result.get("message", result.get("response", response.message))
                    else:
                        actual_message = response.message
                else:
                    actual_message = response.message
                    
            except (json.JSONDecodeError, KeyError):
                actual_message = response.message
            
            # Log the response
            context.log.log(
                type="agent_response",
                heading=f"Response from {agent_info} ({protocol})",
                content=actual_message,
                kvps={
                    "agent_id": agent_info,
                    "endpoint": endpoint,
                    "protocol": protocol,
                    "routing": "subordinate"
                },
                id=message_id,
            )
            
            # Create a deferred task that returns the response
            task = DeferredTask(thread_name="AgentRouting")
            task.start_task(self._return_response, actual_message)
            
            return task, context
            
        except Exception as e:
            # If routing fails, log error and fallback to main agent
            PrintStyle(
                background_color="#E74C3C", font_color="white", bold=True, padding=True
            ).print(f"Agent routing failed: {str(e)}")
            
            context.log.log(
                type="error",
                heading="Agent Routing Failed",
                content=f"Failed to route to {agent_info} via {protocol}: {str(e)}. Falling back to main agent.",
                kvps={
                    "agent_id": agent_info,
                    "endpoint": endpoint,
                    "protocol": protocol,
                    "error": str(e)
                }
            )
            
            # Disable routing and fallback to main agent
            context.get_agent().set_data("agent_routing_enabled", False)
            return context.communicate(UserMessage(message, attachment_paths)), context
    
    async def _return_response(self, response: str) -> str:
        """Simple async method to return a response."""
        return response
