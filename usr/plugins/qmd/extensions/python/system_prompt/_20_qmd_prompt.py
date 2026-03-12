# usr/plugins/qmd/extensions/python/system_prompt/_20_qmd_prompt.py
"""Inject QMD tool documentation into the agent system prompt."""
from __future__ import annotations

from helpers.extension import Extension
from helpers import cache
from agent import LoopData

_CACHE_AREA = "qmd_prompt_cache"
_COLLECTION_CACHE_KEY = "collections"


class QMDPrompt(Extension):

    async def execute(
        self,
        system_prompt: list[str] = [],
        loop_data: LoopData = LoopData(),
        **kwargs,
    ):
        if not self.agent:
            return

        # Get collections — cached per session to avoid bridge call every message
        collections_str = await self._get_collections()

        prompt_text = self.agent.read_prompt(
            "qmd_tools.md",
            collections=collections_str,
        )
        system_prompt.append(prompt_text)

    async def _get_collections(self) -> str:
        """Return a comma-separated list of collection names, cached per session."""
        # cache.get(area, key) — returns None if not found
        cached = cache.get(_CACHE_AREA, _COLLECTION_CACHE_KEY)
        if cached:
            return cached

        try:
            from usr.plugins.qmd.helpers.client_access import get_or_create_client
            client = await get_or_create_client(self.agent)
            result = await client.call("collection_list")
            collections = result.get("collections", [])
            names = ", ".join(c.get("name", "") for c in collections) or "none"
        except Exception:
            names = "unknown (bridge not running)"

        # cache.add(area, key, data) — no TTL support
        cache.add(_CACHE_AREA, _COLLECTION_CACHE_KEY, names)
        return names
