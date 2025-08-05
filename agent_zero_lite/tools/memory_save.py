import os
import json
from datetime import datetime
from helpers.tool import Tool, Response
from helpers.files import get_abs_path


class MemorySave(Tool):
    """
    Tool for saving information to memory.
    """
    async def execute(self, text="", area="main", **kwargs):
        # Create a simple memory entry
        memory_id = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Create memory directory if it doesn't exist
        memory_dir = get_abs_path("memory")
        os.makedirs(memory_dir, exist_ok=True)
        
        # Create area directory if it doesn't exist
        area_dir = os.path.join(memory_dir, area)
        os.makedirs(area_dir, exist_ok=True)
        
        # Create memory file
        memory_file = os.path.join(area_dir, f"{memory_id}.json")
        
        # Create memory data
        memory_data = {
            "id": memory_id,
            "text": text,
            "area": area,
            "created_at": datetime.now().isoformat(),
            "metadata": kwargs
        }
        
        # Save memory data
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=2)
        
        result = f"Memory saved with ID: {memory_id}"
        return Response(message=result, break_loop=False)