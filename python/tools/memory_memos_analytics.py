"""
MemOS analytics tool for getting memory insights and statistics.
"""

from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response


class MemoryMemOSAnalytics(Tool):
    """Tool to get analytics and insights about memories stored in MemOS."""

    async def execute(self, **kwargs):
        db = await Memory.get(self.agent)
        
        # Check if we're using MemOS backend
        if not hasattr(db, 'client') or not hasattr(db.client, 'client'):
            return Response(
                message="MemOS analytics are only available when using MemOS backend. Current backend: FAISS",
                break_loop=False
            )
        
        try:
            # Get memory statistics for this user
            user_id = db.client.user_id
            
            # Search for all memories to get count by area
            all_memories = await db.search_similarity_threshold(
                query="*", limit=1000, threshold=0.1, filter=""
            )
            
            # Analyze memories by area
            area_counts = {}
            total_memories = len(all_memories)
            
            for memory in all_memories:
                area = memory.metadata.get("area", "unknown")
                area_counts[area] = area_counts.get(area, 0) + 1
            
            # Format analytics response
            analytics = [
                f"**MemOS Memory Analytics for {user_id}**",
                f"",
                f"📊 **Memory Statistics:**",
                f"• Total memories: {total_memories}",
                f"• Memory cube: {db.client.memory_cube_id}",
                f"• Memory subdirectory: {db.memory_subdir}",
                f"",
                f"📁 **Memories by Area:**"
            ]
            
            for area, count in sorted(area_counts.items()):
                percentage = (count / total_memories * 100) if total_memories > 0 else 0
                analytics.append(f"• {area}: {count} memories ({percentage:.1f}%)")
            
            if db.client.metadata_enrichment:
                analytics.extend([
                    f"",
                    f"⚙️ **Configuration:**",
                    f"• Metadata enrichment: Enabled",
                    f"• Auto memory creation: {'Enabled' if db.client.auto_memory_creation else 'Disabled'}",
                    f"• Model: {db.client.model_config.provider.name}/{db.client.model_config.name}"
                ])
            
            result = "\n".join(analytics)
            
        except Exception as e:
            result = f"Error retrieving MemOS analytics: {str(e)}"
        
        return Response(message=result, break_loop=False)