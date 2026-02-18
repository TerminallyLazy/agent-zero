"""
EdgeQuake conversation indexing extension.

Fires after each agent monologue. Buffers conversation turns and uploads
them to EdgeQuake for knowledge graph indexing when the buffer reaches
the configured batch size.

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
_DATA_BUFFER = "_edgequake_index_buffer"
_DATA_HASHES = "_edgequake_index_hashes"


def _content_hash(text: str) -> str:
    """MD5 hash for deduplication."""
    return hashlib.md5(text.encode()).hexdigest()


class EdgequakeIndex(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            from plugins.edgequake.helpers.edgequake_client import (
                get_edgequake_client,
                get_edgequake_settings,
            )

            settings = get_edgequake_settings()
            if not settings.get("auto_index", False):
                return

            client = get_edgequake_client()
            if client is None:
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

            # Get per-agent buffer and hash set
            buffer = self.agent.get_data(_DATA_BUFFER)
            if buffer is None:
                buffer = []
                self.agent.set_data(_DATA_BUFFER, buffer)

            hashes = self.agent.get_data(_DATA_HASHES)
            if hashes is None:
                hashes = set()
                self.agent.set_data(_DATA_HASHES, hashes)

            # Deduplicate by content hash
            h = _content_hash(content)
            if h in hashes:
                return

            # Buffer the turn (hash added only after successful flush)
            buffer.append({
                "content": content,
                "title": "Conversation turn",
                "hash": h,
            })

            batch_size = int(settings.get("index_batch_size", 5))
            if batch_size < 1:
                batch_size = 1

            if len(buffer) >= batch_size:
                await self._flush(client, buffer, hashes)

        except Exception as e:
            # Non-blocking: log and continue
            PrintStyle.error(f"EdgeQuake indexing error: {e}")

    async def _flush(self, client, buffer: list, hashes: set) -> None:
        """Upload buffered turns to EdgeQuake."""
        if not buffer:
            return

        batch = list(buffer)
        buffer.clear()

        log_item = self.agent.context.log.log(
            type="util",
            heading=f"EdgeQuake: indexing {len(batch)} conversation turns...",
        )

        try:
            for turn in batch:
                await asyncio.to_thread(
                    client.documents.upload,
                    content=turn["content"],
                    title=turn["title"],
                )
                # Only mark as indexed after successful upload
                hashes.add(turn["hash"])

            # Cap hash set to prevent unbounded growth
            if len(hashes) > 10000:
                hashes.clear()

            log_item.update(
                heading=f"EdgeQuake: indexed {len(batch)} turns",
            )
        except Exception as e:
            # Restore un-uploaded turns for retry on next flush
            buffer.extend(batch)
            log_item.update(
                heading=f"EdgeQuake: indexing failed — {str(e)}",
            )
