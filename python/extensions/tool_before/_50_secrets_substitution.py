"""
Secrets substitution extension for tool execution.
Handles placeholder substitution before tool execution and response sanitization after.
"""

from typing import Any
from python.helpers.extension import Extension
from python.helpers.secrets import SecretsManager
from agent import Agent, LoopData


class SecretsSubstitution(Extension):
    """Extension that handles secrets placeholder substitution for tools"""

    async def execute(self, tool: Any = None, **kwargs: Any):
        """
        Replace placeholders in tool arguments with actual secret values
        This runs before tool execution
        """
        if tool and hasattr(tool, 'args') and tool.args:
            try:
                # Replace placeholders in tool arguments with strict mode
                # This will raise RepairableException if placeholders are missing
                tool.args = SecretsManager.replace_placeholders_in_dict(tool.args, strict=True)
            except Exception as e:
                # If it's a RepairableException from missing secrets, re-raise it
                if "RepairableException" in str(type(e)):
                    raise e
                # For other errors, fail silently to avoid breaking tools
                pass