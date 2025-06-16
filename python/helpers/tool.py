from abc import abstractmethod
from dataclasses import dataclass

from agent import Agent
from python.helpers.print_style import PrintStyle
from python.helpers.strings import sanitize_string
from python.helpers.secrets import SecretsManager


@dataclass
class Response:
    message:str
    break_loop: bool

class Tool:

    def __init__(self, agent: Agent, name: str, method: str | None, args: dict[str,str], message: str, **kwargs) -> None:
        self.agent = agent
        self.name = name
        self.method = method
        self.args = args
        self.message = message

    async def execute(self, **kwargs) -> Response:
        """Main execute method with secrets placeholder substitution"""
        # Replace placeholders in kwargs with actual secret values
        processed_kwargs = SecretsManager.replace_placeholders_in_dict(kwargs)
        
        # Execute the actual tool implementation
        response = await self._execute_impl(**processed_kwargs)
        
        # Replace any secret values in the response message with placeholders for logging
        if response and response.message:
            response.message = SecretsManager.replace_values_with_placeholders(response.message)
        
        return response

    @abstractmethod
    async def _execute_impl(self, **kwargs) -> Response:
        """Tool implementation - override this method in subclasses"""
        pass

    async def before_execution(self, **kwargs):
        PrintStyle(font_color="#1B4F72", padding=True, background_color="white", bold=True).print(f"{self.agent.agent_name}: Using tool '{self.name}'")
        self.log = self.get_log_object()
        if self.args and isinstance(self.args, dict):
            for key, value in self.args.items():
                PrintStyle(font_color="#85C1E9", bold=True).stream(self.nice_key(key)+": ")
                PrintStyle(font_color="#85C1E9", padding=isinstance(value,str) and "\n" in value).stream(value)
                PrintStyle().print()

    async def after_execution(self, response: Response, **kwargs):
        text = sanitize_string(response.message.strip())
        self.agent.hist_add_tool_result(self.name, text)
        PrintStyle(font_color="#1B4F72", background_color="white", padding=True, bold=True).print(f"{self.agent.agent_name}: Response from tool '{self.name}'")
        PrintStyle(font_color="#85C1E9").print(text)
        self.log.update(content=text)

    def get_log_object(self):
        if self.method:
            heading = f"{self.agent.agent_name}: Using tool '{self.name}:{self.method}'"
        else:
            heading = f"{self.agent.agent_name}: Using tool '{self.name}'"
        return self.agent.context.log.log(type="tool", heading=heading, content="", kvps=self.args)

    def nice_key(self, key:str):
        words = key.split('_')
        words = [words[0].capitalize()] + [word.lower() for word in words[1:]]
        result = ' '.join(words)
        return result
