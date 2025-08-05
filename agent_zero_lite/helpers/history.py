from typing import Dict, List, Any, Optional
from helpers import tokens


class Message:
    def __init__(self, content: str, ai: bool = False, tool_name: Optional[str] = None):
        self.content = content
        self.ai = ai
        self.tool_name = tool_name
        self.token_count = tokens.approximate_tokens(content)

    def to_dict(self) -> Dict[str, Any]:
        if self.tool_name:
            return {
                "role": "function",
                "name": self.tool_name,
                "content": self.content
            }
        elif self.ai:
            return {
                "role": "assistant",
                "content": self.content
            }
        else:
            return {
                "role": "user",
                "content": self.content
            }


class History:
    def __init__(self, agent: Any):
        self.agent = agent
        self.messages: List[Message] = []
        self.max_tokens = 4000  # Default token limit

    def add_user_message(self, content: str) -> Message:
        message = Message(content=content, ai=False)
        self.messages.append(message)
        return message

    def add_ai_message(self, content: str) -> Message:
        message = Message(content=content, ai=True)
        self.messages.append(message)
        return message

    def add_tool_result(self, tool_name: str, content: str) -> Message:
        message = Message(content=content, ai=False, tool_name=tool_name)
        self.messages.append(message)
        return message

    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """
        Get messages formatted for the LLM, with simple token management.
        """
        formatted_messages = [msg.to_dict() for msg in self.messages]
        
        # Simple token management - if we exceed the limit, remove oldest messages
        total_tokens = sum(msg.token_count for msg in self.messages)
        
        if total_tokens > self.max_tokens:
            # Keep removing messages from the beginning until we're under the limit
            # Always keep the most recent user message
            while total_tokens > self.max_tokens and len(formatted_messages) > 1:
                removed_msg = self.messages.pop(0)
                total_tokens -= removed_msg.token_count
                formatted_messages = [msg.to_dict() for msg in self.messages]
        
        return formatted_messages