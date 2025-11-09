from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers.acp_client import ACPConnection


class ACPAgent(Tool):
    """
    Communicate with another ACP-compatible agent.

    This tool allows Agent Zero to connect to and interact with external
    ACP (Agent Client Protocol) agents as a client.
    """

    async def execute(self, **kwargs):
        """
        Execute communication with an ACP agent.

        Args:
            command: Command to spawn ACP agent (e.g., "python agent.py")
            message: User message to send (required)
            attachments: Comma-separated file paths (optional)
            reset: Clear session and reconnect (default: False)

        Returns:
            Response from the ACP agent
        """
        command: str | None = kwargs.get("command")  # required
        user_message: str | None = kwargs.get("message")  # required
        attachments_str: str | None = kwargs.get("attachments")  # optional CSV
        reset = bool(kwargs.get("reset", False))

        # Validate required arguments
        if not command or not isinstance(command, str):
            return Response(message="command argument missing or invalid", break_loop=False)
        if not user_message or not isinstance(user_message, str):
            return Response(message="message argument missing or invalid", break_loop=False)

        # Parse attachments
        attachments = []
        if attachments_str and isinstance(attachments_str, str):
            attachments = [a.strip() for a in attachments_str.split(",") if a.strip()]

        # Parse command string to list
        command_parts = command.split()

        # Retrieve or create session cache on the Agent instance
        # Key format: command joined by spaces for simplicity
        sessions: dict[str, ACPConnection] = self.agent.get_data("_acp_sessions") or {}
        command_key = " ".join(command_parts)

        # Handle reset flag – close and remove existing connection
        if reset and command_key in sessions:
            try:
                old_conn = sessions.pop(command_key)
                await old_conn.close()
                PrintStyle(font_color="cyan").print(f"[ACP Agent Tool] Reset connection to: {command_key}")
            except Exception as e:
                PrintStyle.error(f"Error closing old connection: {e}")

        # Get or create connection
        connection = sessions.get(command_key)

        try:
            # Create new connection if needed
            if not connection:
                PrintStyle(font_color="cyan").print(f"[ACP Agent Tool] Creating connection to: {command_key}")
                connection = ACPConnection(command_parts)
                await connection.connect()
                sessions[command_key] = connection
                self.agent.set_data("_acp_sessions", sessions)

            # Send prompt to ACP agent
            response_text = await connection.prompt(user_message, attachments)

            return Response(message=response_text or "(no response)", break_loop=False)

        except Exception as e:
            PrintStyle.error(f"ACP agent error: {e}")

            # Clean up failed connection
            if command_key in sessions:
                try:
                    failed_conn = sessions.pop(command_key)
                    await failed_conn.close()
                except Exception:
                    pass
                self.agent.set_data("_acp_sessions", sessions)

            return Response(message=f"ACP agent error: {e}", break_loop=False)
