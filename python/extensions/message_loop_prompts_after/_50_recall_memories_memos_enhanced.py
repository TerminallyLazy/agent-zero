"""
Enhanced memory recall extension with MemOS-specific optimizations.

This extension enhances the standard memory recall with MemOS-specific features
like metadata-based filtering, enhanced relevance scoring, and memory analytics.
"""

import asyncio
from typing import Dict, Any, List
from python.helpers.extension import Extension
from python.helpers.memory import Memory
from python.helpers.print_style import PrintStyle
from agent import LoopData

DATA_NAME_TASK = "_recall_memories_memos_enhanced_task"


class RecallMemoriesMemOSEnhanced(Extension):
    """Enhanced memory recall extension leveraging MemOS capabilities."""

    INTERVAL = 3
    HISTORY = 10000
    RESULTS = 5  # Increased for MemOS
    THRESHOLD = 0.6
    ENABLE_ANALYTICS = True
    MEMORY_SCORE_BOOST = 0.1  # Boost for recent memories

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        """Execute enhanced memory recall with MemOS optimizations."""
        
        # Check if we're using MemOS backend
        db = await Memory.get(self.agent)
        is_memos = hasattr(db, 'client') and hasattr(db.client, 'client')
        
        if not is_memos:
            # Fall back to standard memory recall if not using MemOS
            from python.extensions.message_loop_prompts_after._50_recall_memories import RecallMemories
            standard_recall = RecallMemories(self.agent)
            return await standard_recall.execute(loop_data, **kwargs)

        # Enhanced MemOS recall every 3 iterations (or the first one)
        if loop_data.iteration % self.INTERVAL == 0:
            task = asyncio.create_task(
                self.search_memories_enhanced(loop_data=loop_data, **kwargs)
            )
        else:
            task = None

        # Set to agent to be able to wait for it
        self.agent.set_data(DATA_NAME_TASK, task)

    async def search_memories_enhanced(self, loop_data: LoopData, **kwargs):
        """Enhanced memory search leveraging MemOS capabilities."""
        
        # Cleanup previous memories
        extras = loop_data.extras_persistent
        if "memories" in extras:
            del extras["memories"]

        try:
            # Enhanced logging
            log_item = self.agent.context.log.log(
                type="util",
                heading="Searching MemOS memories (enhanced)...",
            )

            # Get conversation context
            msgs_text = self.agent.history.output_text()[-self.HISTORY:]
            
            # Enhanced query generation with MemOS context
            system_prompt = self.agent.read_prompt(
                "memory.memories_query.sys.md", 
                history=msgs_text,
                memory_backend="MemOS",
                enhanced_features="metadata filtering, relevance scoring, temporal weighting"
            )

            # Log query generation
            async def log_callback(content):
                log_item.stream(query=content)

            # Generate enhanced search query
            query = await self.agent.call_utility_model(
                system=system_prompt,
                message=(
                    loop_data.user_message.output_text() if loop_data.user_message else "None"
                ),
                callback=log_callback,
            )

            # Get MemOS database
            db = await Memory.get(self.agent)
            
            # Perform enhanced multi-area search
            memories = await self._search_memories_multi_area(db, query, log_item)
            
            if not memories:
                log_item.update(heading="No useful memories found")
                return

            # Apply MemOS-specific enhancements
            enhanced_memories = await self._enhance_memory_results(db, memories, query)
            
            log_item.update(
                heading=f"{len(enhanced_memories)} enhanced memories found",
            )

            # Format memories with enhanced metadata
            memories_text = self._format_enhanced_memories(enhanced_memories)
            
            # Log the full results
            log_item.update(memories=memories_text)

            # Generate enhanced prompt with MemOS context
            memories_prompt = self.agent.parse_prompt(
                "agent.system.memories.md", 
                memories=memories_text,
                memory_backend="MemOS",
                memory_count=len(enhanced_memories)
            )

            # Add to prompt
            extras["memories"] = memories_prompt

            # Optional: Add memory analytics if enabled
            if self.ENABLE_ANALYTICS:
                await self._add_memory_analytics(extras, db)

        except Exception as e:
            PrintStyle.error(f"Enhanced memory recall error: {e}")
            # Fall back to basic search
            await self._fallback_search(loop_data, extras)

    async def _search_memories_multi_area(self, db, query: str, log_item) -> List[Any]:
        """Perform multi-area memory search with MemOS optimizations."""
        
        # Search main and fragments areas with different weights
        searches = [
            {
                "filter": f"area == '{Memory.Area.MAIN.value}'",
                "weight": 1.2,  # Boost main memories
                "label": "main"
            },
            {
                "filter": f"area == '{Memory.Area.FRAGMENTS.value}'",
                "weight": 1.0,
                "label": "fragments"
            }
        ]
        
        all_memories = []
        
        for search in searches:
            try:
                memories = await db.search_similarity_threshold(
                    query=query,
                    limit=self.RESULTS,
                    threshold=self.THRESHOLD,
                    filter=search["filter"]
                )
                
                # Apply area-specific weighting
                for memory in memories:
                    if hasattr(memory, 'metadata'):
                        memory.metadata['search_weight'] = search["weight"]
                        memory.metadata['search_area'] = search["label"]
                
                all_memories.extend(memories)
                
            except Exception as e:
                PrintStyle.error(f"Error searching {search['label']} area: {e}")
        
        # Remove duplicates and sort by relevance
        unique_memories = self._deduplicate_memories(all_memories)
        
        # Return top results
        return unique_memories[:self.RESULTS]

    async def _enhance_memory_results(self, db, memories: List[Any], query: str) -> List[Dict[str, Any]]:
        """Apply MemOS-specific enhancements to memory results."""
        
        enhanced_memories = []
        
        for memory in memories:
            enhanced = {
                "content": memory.page_content,
                "metadata": memory.metadata,
                "relevance_score": self._calculate_relevance_score(memory, query),
                "temporal_score": self._calculate_temporal_score(memory),
                "area": memory.metadata.get("area", "unknown")
            }
            
            # Add MemOS-specific metadata if available
            if hasattr(db, 'client'):
                enhanced["memory_cube"] = getattr(db.client, 'memory_cube_id', 'unknown')
                enhanced["user_id"] = getattr(db.client, 'user_id', 'unknown')
            
            enhanced_memories.append(enhanced)
        
        # Sort by combined score
        enhanced_memories.sort(
            key=lambda x: x["relevance_score"] + x["temporal_score"], 
            reverse=True
        )
        
        return enhanced_memories

    def _calculate_relevance_score(self, memory, query: str) -> float:
        """Calculate relevance score with MemOS-specific factors."""
        base_score = 0.5  # Default relevance
        
        # Boost based on area
        area = memory.metadata.get("area", "")
        if area == Memory.Area.MAIN.value:
            base_score += 0.2
        elif area == Memory.Area.SOLUTIONS.value:
            base_score += 0.15
        
        # Boost based on search weight
        search_weight = memory.metadata.get("search_weight", 1.0)
        base_score *= search_weight
        
        return min(1.0, base_score)

    def _calculate_temporal_score(self, memory) -> float:
        """Calculate temporal relevance score."""
        from datetime import datetime, timedelta
        
        try:
            timestamp_str = memory.metadata.get("timestamp", "")
            if not timestamp_str:
                return 0.0
            
            memory_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            days_old = (now - memory_time).days
            
            # More recent memories get higher scores
            if days_old <= 1:
                return self.MEMORY_SCORE_BOOST
            elif days_old <= 7:
                return self.MEMORY_SCORE_BOOST * 0.7
            elif days_old <= 30:
                return self.MEMORY_SCORE_BOOST * 0.4
            else:
                return 0.0
                
        except Exception:
            return 0.0

    def _deduplicate_memories(self, memories: List[Any]) -> List[Any]:
        """Remove duplicate memories based on content similarity."""
        if not memories:
            return []
        
        unique_memories = []
        seen_contents = set()
        
        for memory in memories:
            content_hash = hash(memory.page_content[:100])  # First 100 chars as fingerprint
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                unique_memories.append(memory)
        
        return unique_memories

    def _format_enhanced_memories(self, enhanced_memories: List[Dict[str, Any]]) -> str:
        """Format enhanced memories with metadata."""
        if not enhanced_memories:
            return ""
        
        formatted_parts = []
        
        for i, memory in enumerate(enhanced_memories, 1):
            content = memory["content"]
            area = memory["area"]
            relevance = memory["relevance_score"]
            
            # Enhanced formatting with scores
            formatted = f"[Memory {i} - {area.title()} | Relevance: {relevance:.2f}]\n{content}"
            formatted_parts.append(formatted)
        
        return "\n\n".join(formatted_parts)

    async def _add_memory_analytics(self, extras: Dict[str, Any], db):
        """Add memory analytics to the prompt context."""
        try:
            # Get basic analytics
            all_memories = await db.search_similarity_threshold(
                query="*", limit=100, threshold=0.1, filter=""
            )
            
            area_counts = {}
            for memory in all_memories:
                area = memory.metadata.get("area", "unknown")
                area_counts[area] = area_counts.get(area, 0) + 1
            
            analytics_text = f"\n[Memory Analytics: {len(all_memories)} total memories"
            for area, count in area_counts.items():
                analytics_text += f", {area}: {count}"
            analytics_text += "]"
            
            # Add to existing memories prompt
            if "memories" in extras:
                extras["memories"] += analytics_text
                
        except Exception as e:
            PrintStyle.error(f"Error generating memory analytics: {e}")

    async def _fallback_search(self, loop_data: LoopData, extras: Dict[str, Any]):
        """Fallback to basic memory search if enhanced search fails."""
        try:
            # Use the standard recall extension as fallback
            from python.extensions.message_loop_prompts_after._50_recall_memories import RecallMemories
            standard_recall = RecallMemories(self.agent)
            await standard_recall.search_memories(loop_data)
            
        except Exception as e:
            PrintStyle.error(f"Fallback memory search also failed: {e}")