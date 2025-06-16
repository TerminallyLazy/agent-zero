from typing import Any
from python.helpers.extension import Extension
from python.helpers.secrets import SecretsManager
from agent import Agent, LoopData


class SecretsPrompt(Extension):

    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs: Any):
        # Get available secret keys
        secret_keys = SecretsManager.get_placeholder_keys()
        
        if secret_keys:
            # Add secrets information to system prompt
            secrets_prompt = self.agent.read_prompt("agent.system.secrets.md", keys=secret_keys)
            system_prompt.append(secrets_prompt)