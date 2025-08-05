import os
import json
import glob
from typing import List, Dict, Any
from helpers.tool import Tool, Response
from helpers.files import get_abs_path


class MemoryLoad(Tool):
    """
    Tool for loading information from memory.
    """
    async def execute(self, query="", area="", limit=10, **kwargs):
        # Get memory directory
        memory_dir = get_abs_path("memory")
        
        # If area is specified, look only in that area
        if area:
            search_path = os.path.join(memory_dir, area, "*.json")
        else:
            # Otherwise search all areas
            search_path = os.path.join(memory_dir, "**", "*.json")
        
        # Find all memory files
        memory_files = glob.glob(search_path, recursive=True)
        
        # Sort by modification time (newest first)
        memory_files.sort(key=os.path.getmtime, reverse=True)
        
        # Limit the number of files
        memory_files = memory_files[:limit]
        
        # Load memory data
        memories = []
        for file_path in memory_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    memory_data = json.load(f)
                
                # Simple text search if query is provided
                if query and query.lower() not in memory_data.get("text", "").lower():
                    continue
                
                memories.append(memory_data)
            except Exception as e:
                print(f"Error loading memory file {file_path}: {str(e)}")
        
        # Format the response
        if not memories:
            result = f"No memories found for query: {query}"
        else:
            result = "Found memories:\n\n"
            for memory in memories:
                result += f"ID: {memory.get('id')}\n"
                result += f"Area: {memory.get('area')}\n"
                result += f"Text: {memory.get('text')}\n"
                result += f"Created: {memory.get('created_at')}\n\n"
        
        return Response(message=result, break_loop=False)