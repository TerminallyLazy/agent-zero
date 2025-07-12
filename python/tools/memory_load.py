from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response

DEFAULT_THRESHOLD = 0.7
DEFAULT_LIMIT = 10


class MemoryLoad(Tool):

    async def execute(self, query="", threshold=DEFAULT_THRESHOLD, limit=DEFAULT_LIMIT, filter="", **kwargs):
        try:
            db = await Memory.get(self.agent)
            
            # Call search with error handling for MemoryOS compatibility
            try:
                docs = await db.search_similarity_threshold(
                    query=query, 
                    limit=limit, 
                    threshold=threshold, 
                    filter=filter
                )
            except TypeError:
                # Fallback for backends that don't support filter parameter
                docs = await db.search_similarity_threshold(
                    query=query, 
                    limit=limit, 
                    threshold=threshold
                )

            if len(docs) == 0:
                result = self.agent.read_prompt("fw.memories_not_found.md", query=query)
            else:
                text = "\n\n".join(Memory.format_docs_plain(docs))
                result = str(text)

            return Response(message=result, break_loop=False)
            
        except Exception as e:
            error_msg = f"Error loading memories: {str(e)}"
            return Response(message=error_msg, break_loop=False)
