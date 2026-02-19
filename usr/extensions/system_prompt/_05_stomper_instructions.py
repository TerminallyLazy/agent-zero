"""Prompt Stomper — System prompt hardening + canary token injection.

Injects security hardening instructions and a per-session canary token
into the system prompt.

Extension point: system_prompt
kwargs: system_prompt (mutable list[str]), loop_data
"""

import os

from python.helpers.extension import Extension
from python.helpers import files


PROMPT_FILE = files.get_abs_path(
    "plugins", "prompt_stomper", "prompts", "stomper.system_hardening.md"
)


class StomperSystemHardening(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data=None, **kwargs):
        from plugins.prompt_stomper.helpers.stomper_settings import get_settings
        from plugins.prompt_stomper.helpers.canary import get_canary_token

        settings = get_settings()
        if not settings.get("enabled") or not settings.get("system_hardening"):
            return

        # Read the hardening prompt template
        if not os.path.exists(PROMPT_FILE):
            return

        with open(PROMPT_FILE, "r") as f:
            template = f.read()

        # Inject canary token
        canary = get_canary_token() if settings.get("canary_tokens") else "DISABLED"
        prompt = template.replace("{{canary_token}}", canary)

        # Append to system prompt (at end, so it's the last instruction the model sees)
        system_prompt.append(prompt)
