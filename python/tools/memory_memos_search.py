"""
Enhanced MemOS search tool with advanced features and metadata support.
"""

from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response


class MemoryMemOSSearch(Tool):
    """Enhanced search tool with MemOS-specific features."""

    async def execute(self, query="", limit=10, threshold=0.7, area_filter="", 
                     include_metadata=False, sort_by_relevance=True, **kwargs):
        
        db = await Memory.get(self.agent)
        
        # Build filter string
        filter_parts = []
        if area_filter:
            filter_parts.append(f"area == '{area_filter}'")
        
        filter_str = " and ".join(filter_parts) if filter_parts else ""
        
        try:
            docs = await db.search_similarity_threshold(
                query=query, 
                limit=limit, 
                threshold=threshold, 
                filter=filter_str
            )
            
            if len(docs) == 0:
                result = self.agent.read_prompt("fw.memories_not_found.md", query=query)
            else:
                # Format results with enhanced information
                formatted_results = []
                
                for i, doc in enumerate(docs, 1):
                    content = doc.page_content
                    metadata = doc.metadata
                    
                    # Basic formatting
                    formatted_result = f"**Memory {i}:**\n{content}"
                    
                    # Add metadata if requested
                    if include_metadata:
                        formatted_result += f"\n*Area: {metadata.get('area', 'unknown')}*"
                        formatted_result += f"\n*Timestamp: {metadata.get('timestamp', 'unknown')}*"
                        
                        # Add MemOS-specific metadata if available
                        if metadata.get('memory_cube'):
                            formatted_result += f"\n*Memory Cube: {metadata.get('memory_cube')}*"
                    
                    formatted_results.append(formatted_result)
                
                result = "\n\n".join(formatted_results)
                
                # Add search summary
                if hasattr(db, 'client'):
                    result = f"🔍 **Found {len(docs)} memories** (threshold: {threshold})\n\n{result}"
        
        except Exception as e:
            result = f"Error searching MemOS: {str(e)}"
        
        return Response(message=result, break_loop=False)