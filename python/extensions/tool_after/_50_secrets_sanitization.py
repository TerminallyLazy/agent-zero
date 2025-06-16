"""
Secrets sanitization extension for tool responses.
Handles sanitization of tool responses to replace secret values with placeholders.
"""

from typing import Any
from python.helpers.extension import Extension
from python.helpers.secrets import SecretsManager
from agent import Agent, LoopData


class SecretsSanitization(Extension):
    """Extension that sanitizes tool responses to replace secret values with placeholders"""

    async def execute(self, response: Any = None, **kwargs: Any):
        """
        Replace secret values in tool responses with placeholders
        This runs after tool execution
        """
        if response and hasattr(response, 'message') and response.message:
            try:
                # Replace secret values with placeholders for safe logging
                response.message = SecretsManager.replace_values_with_placeholders(response.message)
            except Exception:
                # Fail silently to avoid breaking tool responses
                pass