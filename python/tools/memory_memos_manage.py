"""
MemOS memory management tool for cleanup, migration, and maintenance operations.
"""

from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response
from datetime import datetime, timedelta


class MemoryMemOSManage(Tool):
    """Memory management tool with MemOS-specific operations."""

    async def execute(self, action="", memory_id="", area="", query="", **kwargs):
        
        if not action:
            return Response(
                message="Please specify an action: 'cleanup', 'migrate_area', 'duplicate_check', or 'export_summary'",
                break_loop=False
            )
        
        db = await Memory.get(self.agent)
        
        try:
            if action == "cleanup":
                # Remove old or low-relevance memories
                result = await self._cleanup_memories(db, **kwargs)
            elif action == "migrate_area":
                # Move memories from one area to another
                result = await self._migrate_area(db, area, **kwargs)
            elif action == "duplicate_check":
                # Find potential duplicate memories
                result = await self._check_duplicates(db, **kwargs)
            elif action == "export_summary":
                # Export memory summary
                result = await self._export_summary(db, **kwargs)
            else:
                result = f"Unknown action: {action}"
        
        except Exception as e:
            result = f"Error during {action}: {str(e)}"
        
        return Response(message=result, break_loop=False)
    
    async def _cleanup_memories(self, db, days_old=30, min_threshold=0.3, **kwargs):
        """Clean up old or irrelevant memories."""
        
        # Find old memories
        cutoff_date = datetime.now() - timedelta(days=days_old)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        # Search for potentially outdated memories
        old_memories = await db.search_similarity_threshold(
            query="outdated temporary cache", 
            limit=100, 
            threshold=min_threshold,
            filter=""
        )
        
        cleaned_count = 0
        for memory in old_memories:
            timestamp_str = memory.metadata.get("timestamp", "")
            if timestamp_str and timestamp_str < cutoff_str:
                memory_id = memory.metadata.get("id")
                if memory_id:
                    await db.delete_documents_by_ids([memory_id])
                    cleaned_count += 1
        
        return f"Cleaned up {cleaned_count} old memories (older than {days_old} days)"
    
    async def _migrate_area(self, db, target_area, source_area="", **kwargs):
        """Migrate memories from one area to another."""
        if not target_area:
            return "Please specify target_area parameter"
        
        filter_str = f"area == '{source_area}'" if source_area else ""
        
        # Find memories to migrate
        memories = await db.search_similarity_threshold(
            query="*", limit=100, threshold=0.1, filter=filter_str
        )
        
        migrated_count = 0
        for memory in memories:
            if memory.metadata.get("area") != target_area:
                # Update area and re-insert
                memory.metadata["area"] = target_area
                await db.insert_documents([memory])
                
                # Delete old version
                old_id = memory.metadata.get("id")
                if old_id:
                    await db.delete_documents_by_ids([old_id])
                
                migrated_count += 1
        
        return f"Migrated {migrated_count} memories to area '{target_area}'"
    
    async def _check_duplicates(self, db, similarity_threshold=0.95, **kwargs):
        """Check for potential duplicate memories."""
        # Get all memories
        all_memories = await db.search_similarity_threshold(
            query="*", limit=500, threshold=0.1, filter=""
        )
        
        duplicates = []
        processed = set()
        
        for i, memory1 in enumerate(all_memories):
            if i in processed:
                continue
                
            content1 = memory1.page_content
            similar_memories = []
            
            for j, memory2 in enumerate(all_memories[i+1:], i+1):
                if j in processed:
                    continue
                    
                content2 = memory2.page_content
                
                # Simple similarity check (could be enhanced)
                if len(content1) > 0 and len(content2) > 0:
                    similarity = len(set(content1.lower().split()) & set(content2.lower().split())) / len(set(content1.lower().split()) | set(content2.lower().split()))
                    
                    if similarity >= similarity_threshold:
                        similar_memories.append((j, content2[:100] + "..."))
                        processed.add(j)
            
            if similar_memories:
                duplicates.append({
                    "original": (i, content1[:100] + "..."),
                    "duplicates": similar_memories
                })
                processed.add(i)
        
        if duplicates:
            result = f"Found {len(duplicates)} potential duplicate groups:\n\n"
            for group in duplicates[:5]:  # Show first 5 groups
                result += f"Original: {group['original'][1]}\n"
                for dup in group['duplicates']:
                    result += f"  Similar: {dup[1]}\n"
                result += "\n"
        else:
            result = "No potential duplicates found"
        
        return result
    
    async def _export_summary(self, db, **kwargs):
        """Export a summary of all memories."""
        # Get memories by area
        areas = [Memory.Area.MAIN.value, Memory.Area.FRAGMENTS.value, 
                Memory.Area.SOLUTIONS.value, Memory.Area.INSTRUMENTS.value]
        
        summary = ["# Memory Export Summary\n"]
        
        for area in areas:
            memories = await db.search_similarity_threshold(
                query="*", limit=50, threshold=0.1, filter=f"area == '{area}'"
            )
            
            if memories:
                summary.append(f"## {area.title()} Area ({len(memories)} memories)\n")
                for i, memory in enumerate(memories[:5], 1):  # Show first 5
                    content = memory.page_content[:200] + "..." if len(memory.page_content) > 200 else memory.page_content
                    summary.append(f"{i}. {content}\n")
                if len(memories) > 5:
                    summary.append(f"... and {len(memories) - 5} more memories\n")
                summary.append("")
        
        return "\n".join(summary)