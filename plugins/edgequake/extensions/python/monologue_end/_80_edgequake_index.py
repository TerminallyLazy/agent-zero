"""
EdgeQuake conversation indexing extension.

Fires after each agent monologue. Sends each conversation turn to
EdgeQuake for knowledge graph indexing immediately (in a background thread).

Guarded by:
- EdgeQuake must be configured (api_key set)
- auto_index must be enabled in plugin settings
- Non-blocking: failures are logged but never interrupt the agent
"""

import asyncio
import hashlib

from python.helpers.extension import Extension
from python.helpers.print_style import PrintStyle
from agent import LoopData


# Agent data keys for per-context state
_DATA_HASHES = "_edgequake_index_hashes"


def _content_hash(text: str) -> str:
    """MD5 hash for deduplication."""
    return hashlib.md5(text.encode()).hexdigest()


class EdgequakeIndex(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            from plugins.edgequake.helpers.edgequake_client import (
                api_request,
                get_edgequake_settings,
            )

            settings = get_edgequake_settings()
            if not settings.get("auto_index", False):
                return

            # Guard: need an API key configured
            if not settings.get("api_key", "").strip():
                return

            # Extract conversation turn from loop_data
            user_text = ""
            if loop_data.user_message:
                user_text = loop_data.user_message.output_text()

            agent_text = loop_data.last_response or ""

            if not user_text and not agent_text:
                return

            # Build content for this turn
            content = ""
            if user_text:
                content += f"User: {user_text}\n\n"
            if agent_text:
                content += f"Assistant: {agent_text}"
            content = content.strip()

            if not content:
                return

            # Deduplicate by content hash
            hashes = self.agent.get_data(_DATA_HASHES)
            if hashes is None:
                hashes = set()
                self.agent.set_data(_DATA_HASHES, hashes)

            h = _content_hash(content)
            if h in hashes:
                return

            # Index immediately in background thread
            log_item = self.agent.context.log.log(
                type="util",
                heading="EdgeQuake: indexing conversation turn...",
            )

            try:
                body = {"content": content, "title": "Conversation turn"}
                result = await asyncio.to_thread(
                    api_request, "POST", "/api/v1/documents", body
                )
                if "error" in result:
                    log_item.update(
                        heading=f"EdgeQuake: indexing failed — {result['error']}",
                    )
                    return

                # Mark as indexed
                hashes.add(h)

                # Cap hash set to prevent unbounded growth
                if len(hashes) > 10000:
                    hashes.clear()

                entity_count = result.get("entity_count", 0)
                rel_count = result.get("relationship_count", 0)
                log_item.update(
                    heading=f"EdgeQuake: indexed ({entity_count} entities, {rel_count} relationships)",
                )
            except Exception as e:
                log_item.update(
                    heading=f"EdgeQuake: indexing failed — {str(e)}",
                )

        except Exception as e:
            # Non-blocking: log and continue
            PrintStyle.error(f"EdgeQuake indexing error: {e}")
