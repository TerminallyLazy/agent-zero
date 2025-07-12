"""
Enhanced memory storage extension with MemOS-specific optimizations.

This extension enhances the standard memory storage with MemOS-specific features
like intelligent memory categorization, metadata enrichment, and duplicate prevention.
"""

import asyncio
from typing import Dict, Any, List
from python.helpers.extension import Extension
from python.helpers.memory import Memory
from python.helpers.dirty_json import DirtyJson
from python.helpers.log import LogItem
from python.helpers.print_style import PrintStyle
from agent import LoopData


class MemorizeMemoriesMemOSEnhanced(Extension):
    """Enhanced memory storage extension leveraging MemOS capabilities."""

    REPLACE_THRESHOLD = 0.9
    ENABLE_SMART_CATEGORIZATION = True
    ENABLE_METADATA_ENRICHMENT = True
    MAX_MEMORY_LENGTH = 1000  # Character limit for individual memories

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        """Execute enhanced memory storage with MemOS optimizations."""
        
        # Check if we're using MemOS backend
        db = await Memory.get(self.agent)
        is_memos = hasattr(db, 'client') and hasattr(db.client, 'client')
        
        if not is_memos:
            # Fall back to standard memory storage if not using MemOS
            from python.extensions.monologue_end._50_memorize_fragments import MemorizeMemories
            standard_memorize = MemorizeMemories(self.agent)
            return await standard_memorize.execute(loop_data, **kwargs)

        # Enhanced MemOS storage
        log_item = self.agent.context.log.log(
            type="util",
            heading="Memorizing information with MemOS enhancement...",
        )

        # Memorize in background with enhancements
        asyncio.create_task(self.memorize_enhanced(loop_data, log_item))

    async def memorize_enhanced(self, loop_data: LoopData, log_item: LogItem, **kwargs):
        """Enhanced memory storage leveraging MemOS capabilities."""
        
        try:
            # Get conversation context
            msgs_text = self.agent.concat_messages(self.agent.history)
            
            # Enhanced system prompt for MemOS
            system_prompt = self.agent.read_prompt(
                "memory.memories_sum.sys.md",
                memory_backend="MemOS",
                smart_categorization=self.ENABLE_SMART_CATEGORIZATION,
                metadata_enrichment=self.ENABLE_METADATA_ENRICHMENT
            )

            # Log extraction process
            async def log_callback(content):
                log_item.stream(content=content)

            # Call utility model to extract memories with enhanced instructions
            memories_json = await self.agent.call_utility_model(
                system=system_prompt,
                message=msgs_text,
                callback=log_callback,
                background=True,
            )

            # Parse and validate memories
            memories = await self._parse_and_validate_memories(memories_json, log_item)
            
            if not memories:
                log_item.update(heading="No new memories extracted")
                return

            # Apply MemOS-specific enhancements
            enhanced_memories = await self._enhance_memories(memories)
            
            # Store memories with intelligent deduplication
            stored_count = await self._store_memories_intelligent(enhanced_memories, log_item)
            
            log_item.update(
                heading=f"Enhanced memory storage complete - {stored_count} memories stored"
            )

        except Exception as e:
            PrintStyle.error(f"Enhanced memory storage error: {e}")
            await self._fallback_storage(loop_data, log_item)

    async def _parse_and_validate_memories(self, memories_json: str, log_item: LogItem) -> List[Dict[str, Any]]:
        """Parse and validate extracted memories."""
        try:
            memories = DirtyJson.parse_string(memories_json)
        except Exception as e:
            log_item.update(heading=f"Failed to parse memories response: {str(e)}")
            return []

        # Normalize to list
        if not isinstance(memories, list):
            if isinstance(memories, (str, dict)):
                memories = [memories]
            else:
                log_item.update(heading="Invalid memories format received.")
                return []

        # Validate and filter memories
        valid_memories = []
        for memory in memories:
            if isinstance(memory, str):
                memory = {"text": memory}
            elif isinstance(memory, dict) and "text" not in memory:
                # Try to find text in common keys
                text_content = memory.get("content") or memory.get("memory") or str(memory)
                memory = {"text": text_content, **memory}
            
            # Validate memory content
            if self._is_valid_memory(memory):
                valid_memories.append(memory)

        return valid_memories

    def _is_valid_memory(self, memory: Dict[str, Any]) -> bool:
        """Validate if a memory is worth storing."""
        text = memory.get("text", "").strip()
        
        # Basic validation
        if not text or len(text) < 10:
            return False
        
        # Filter out common non-useful memories
        skip_patterns = [
            "hello", "hi", "thanks", "okay", "yes", "no",
            "i understand", "got it", "sure", "alright"
        ]
        
        text_lower = text.lower()
        if any(pattern in text_lower for pattern in skip_patterns) and len(text) < 50:
            return False
        
        # Length validation
        if len(text) > self.MAX_MEMORY_LENGTH:
            memory["text"] = text[:self.MAX_MEMORY_LENGTH] + "..."
        
        return True

    async def _enhance_memories(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply MemOS-specific enhancements to memories."""
        enhanced_memories = []
        
        for memory in memories:
            enhanced = memory.copy()
            
            # Smart categorization
            if self.ENABLE_SMART_CATEGORIZATION:
                category = self._categorize_memory(memory["text"])
                enhanced["suggested_area"] = category
            
            # Metadata enrichment
            if self.ENABLE_METADATA_ENRICHMENT:
                enhanced.update(self._enrich_metadata(memory))
            
            # Add MemOS-specific metadata
            enhanced.update({
                "extraction_method": "enhanced_memos",
                "conversation_length": len(self.agent.history),
                "agent_context": self.agent.memory_subdir or "default"
            })
            
            enhanced_memories.append(enhanced)
        
        return enhanced_memories

    def _categorize_memory(self, text: str) -> str:
        """Intelligently categorize memory content."""
        text_lower = text.lower()
        
        # Solution indicators
        solution_keywords = [
            "solution", "fix", "solved", "resolved", "answer", "how to",
            "step", "method", "approach", "technique", "way to"
        ]
        
        # Preference indicators  
        preference_keywords = [
            "prefer", "like", "dislike", "favorite", "hate", "love",
            "usually", "always", "never", "typically"
        ]
        
        # Fact indicators
        fact_keywords = [
            "fact", "information", "data", "detail", "note",
            "remember", "important", "key", "significant"
        ]
        
        if any(keyword in text_lower for keyword in solution_keywords):
            return Memory.Area.SOLUTIONS.value
        elif any(keyword in text_lower for keyword in preference_keywords):
            return Memory.Area.MAIN.value
        elif any(keyword in text_lower for keyword in fact_keywords):
            return Memory.Area.MAIN.value
        else:
            return Memory.Area.FRAGMENTS.value

    def _enrich_metadata(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich memory with additional metadata."""
        text = memory["text"]
        
        enriched = {
            "text_length": len(text),
            "word_count": len(text.split()),
            "contains_question": "?" in text,
            "contains_code": any(marker in text for marker in ["```", "def ", "function", "import", "class "]),
            "urgency_level": self._assess_urgency(text),
            "topic_keywords": self._extract_keywords(text)
        }
        
        return enriched

    def _assess_urgency(self, text: str) -> str:
        """Assess the urgency level of the memory."""
        text_lower = text.lower()
        
        urgent_keywords = ["urgent", "important", "critical", "asap", "emergency", "priority"]
        medium_keywords = ["soon", "needed", "required", "should"]
        
        if any(keyword in text_lower for keyword in urgent_keywords):
            return "high"
        elif any(keyword in text_lower for keyword in medium_keywords):
            return "medium"
        else:
            return "low"

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract key topics/keywords from the text."""
        # Simple keyword extraction (could be enhanced with NLP)
        import re
        
        # Remove common words and extract meaningful terms
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        
        # Filter out common words
        common_words = {
            "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
            "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
            "how", "its", "may", "new", "now", "old", "see", "two", "who", "boy",
            "did", "its", "let", "put", "say", "she", "too", "use"
        }
        
        keywords = [word for word in set(words) if word not in common_words]
        return keywords[:5]  # Return top 5 keywords

    async def _store_memories_intelligent(self, memories: List[Dict[str, Any]], log_item: LogItem) -> int:
        """Store memories with intelligent deduplication using MemOS."""
        db = await Memory.get(self.agent)
        stored_count = 0
        
        for memory in memories:
            try:
                text = memory["text"]
                area = memory.get("suggested_area", Memory.Area.FRAGMENTS.value)
                
                # Check for duplicates with higher threshold for MemOS
                existing_similar = await db.search_similarity_threshold(
                    query=text,
                    limit=5,
                    threshold=self.REPLACE_THRESHOLD,
                    filter=f"area == '{area}'"
                )
                
                # Remove highly similar memories
                if existing_similar:
                    similar_ids = [doc.metadata.get("id") for doc in existing_similar if doc.metadata.get("id")]
                    if similar_ids:
                        await db.delete_documents_by_ids(similar_ids)
                        log_item.stream(content=f"Replaced {len(similar_ids)} similar memories")
                
                # Prepare metadata
                metadata = {
                    "area": area,
                    **{k: v for k, v in memory.items() if k != "text"}
                }
                
                # Store the memory
                memory_id = await db.insert_text(text, metadata)
                stored_count += 1
                
                log_item.stream(content=f"Stored memory in {area}: {text[:100]}...")
                
            except Exception as e:
                PrintStyle.error(f"Error storing memory: {e}")
        
        return stored_count

    async def _fallback_storage(self, loop_data: LoopData, log_item: LogItem):
        """Fallback to standard memory storage if enhanced storage fails."""
        try:
            from python.extensions.monologue_end._50_memorize_fragments import MemorizeMemories
            standard_memorize = MemorizeMemories(self.agent)
            await standard_memorize.memorize(loop_data, log_item)
            
        except Exception as e:
            PrintStyle.error(f"Fallback memory storage also failed: {e}")
            log_item.update(heading="Memory storage failed")