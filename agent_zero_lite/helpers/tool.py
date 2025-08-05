from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional

from helpers.strings import sanitize_string


@dataclass
class Response:
    message: str
    break_loop: bool


class Tool:
    def __init__(self, agent: Any, name: str, method: Optional[str], args: Dict[str, Any], message: str, loop_data: Any, **kwargs) -> None:
        self.agent = agent
        self.name = name
        self.method = method
        self.args = args
        self.loop_data = loop_data
        self.message = message

    @abstractmethod
    async def execute(self, **kwargs) -> Response:
        pass

    async def before_execution(self, **kwargs):
        print(f"{self.agent.agent_name}: Using tool '{self.name}'")
        if self.args and isinstance(self.args, dict):
            for key, value in self.args.items():
                print(f"{self.nice_key(key)}: {value}")

    async def after_execution(self, response: Response, **kwargs):
        text = sanitize_string(response.message.strip())
        self.agent.hist_add_tool_result(self.name, text)
        print(f"{self.agent.agent_name}: Response from tool '{self.name}'")
        print(text)

    def nice_key(self, key: str):
        words = key.split('_')
        words = [words[0].capitalize()] + [word.lower() for word in words[1:]]
        result = ' '.join(words)
        return result