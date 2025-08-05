import asyncio
import nest_asyncio
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable, Coroutine

nest_asyncio.apply()

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage

import models
from helpers import history, tokens, files, extract_tools
from helpers.tool import Tool, Response
from helpers.extension import call_extensions
from helpers.log import Log


class AgentContextType(Enum):
    USER = "user"
    TASK = "task"
    BACKGROUND = "background"


class AgentContext:
    _contexts: dict[str, "AgentContext"] = {}
    _counter: int = 0

    def __init__(
        self,
        config: "AgentConfig",
        id: str | None = None,
        name: str | None = None,
        agent0: "Agent|None" = None,
        log: Log | None = None,
        paused: bool = False,
        created_at: datetime | None = None,
        type: AgentContextType = AgentContextType.USER,
        last_message: datetime | None = None,
    ):
        # build context
        self.id = id or str(uuid.uuid4())
        self.name = name
        self.config = config
        self.log = log or Log()
        self.agent0 = agent0 or Agent(0, self.config, self)
        self.paused = paused
        self.created_at = created_at or datetime.now(timezone.utc)
        self.type = type
        AgentContext._counter += 1
        self.no = AgentContext._counter
        # set to start of unix epoch
        self.last_message = last_message or datetime.now(timezone.utc)

        existing = self._contexts.get(self.id, None)
        if existing:
            AgentContext.remove(self.id)
        self._contexts[self.id] = self

    @staticmethod
    def get(id: str):
        return AgentContext._contexts.get(id, None)

    @staticmethod
    def first():
        if not AgentContext._contexts:
            return None
        return list(AgentContext._contexts.values())[0]

    @staticmethod
    def all():
        return list(AgentContext._contexts.values())

    @staticmethod
    def remove(id: str):
        context = AgentContext._contexts.pop(id, None)
        if context:
            return True
        return False


@dataclass
class AgentConfig:
    chat_model: models.ModelConfig
    utility_model: models.ModelConfig
    mcp_servers: str = ""
    profile: str = ""
    memory_subdir: str = ""


class UserMessage:
    def __init__(self, message: str, attachments: List[Any] = None):
        self.message = message
        self.attachments = attachments or []


class RepairableException(Exception):
    pass


class HandledException(Exception):
    pass


@dataclass
class LoopData:
    params_temporary: Dict[str, Any] = field(default_factory=dict)
    params_persistent: Dict[str, Any] = field(default_factory=dict)


class Agent:
    DATA_NAME_SUPERIOR = "_superior"
    DATA_NAME_SUBORDINATE = "_subordinate"
    DATA_NAME_CTX_WINDOW = "ctx_window"

    def __init__(
        self, number: int, config: AgentConfig, context: AgentContext | None = None
    ):
        # agent config
        self.config = config

        # agent context
        self.context = context or AgentContext(config=config, agent0=self)

        # non-config vars
        self.number = number
        self.agent_name = f"A{self.number}"

        self.history = history.History(self)
        self.last_user_message: history.Message | None = None
        self.intervention: UserMessage | None = None
        self.data = {}  # free data object all the tools can use

        asyncio.run(self.call_extensions("agent_init"))

    async def call_extensions(self, extension_point: str, **kwargs):
        await call_extensions(extension_point, self, **kwargs)

    def set_data(self, key: str, value: Any):
        self.data[key] = value

    def get_data(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def hist_add_user_message(self, message: UserMessage):
        self.last_user_message = self.history.add_user_message(message.message)
        self.context.last_message = datetime.now(timezone.utc)
        return self.last_user_message

    def hist_add_tool_result(self, tool_name: str, tool_result: str):
        return self.history.add_tool_result(tool_name, tool_result)

    def hist_add_ai_message(self, message: str):
        return self.history.add_ai_message(message)

    async def handle_intervention(self):
        if self.intervention:
            intervention = self.intervention
            self.intervention = None
            self.hist_add_user_message(intervention)
            await self.monologue()

    def read_prompt(self, file: str, **kwargs) -> str:
        prompt_dir = files.get_abs_path("prompts")
        backup_dir = []
        if self.config.profile:
            prompt_dir = files.get_abs_path("agents", self.config.profile, "prompts")
            backup_dir.append(files.get_abs_path("prompts"))
        prompt = files.read_prompt_file(
            files.get_abs_path(prompt_dir, file), _backup_dirs=backup_dir, **kwargs
        )
        prompt = files.remove_code_fences(prompt)
        return prompt

    async def build_system_prompt(self) -> str:
        system_prompt = ""
        await self.call_extensions("system_prompt", system_prompt_text=system_prompt)
        return system_prompt

    async def monologue(self) -> str:
        await self.call_extensions("monologue_start")

        loop_data = LoopData()
        await self.call_extensions("message_loop_start", loop_data=loop_data)

        try:
            response = await self.message_loop(loop_data)
            await self.call_extensions("monologue_end", response=response)
            return response
        except Exception as e:
            self.handle_critical_exception(e)
            return str(e)

    async def message_loop(self, loop_data: LoopData) -> str:
        system_prompt = await self.build_system_prompt()
        messages = self.history.get_messages_for_llm()
        
        while True:
            await self.call_extensions("message_loop_before_llm", loop_data=loop_data)
            
            response = await models.chat_completion(
                self.config.chat_model,
                system_prompt,
                messages,
                stream=True,
                callback=self.stream_callback,
            )
            
            await self.call_extensions("message_loop_after_llm", loop_data=loop_data, response=response)
            
            try:
                tool_calls = extract_tools.extract_tool_calls(response)
                
                if not tool_calls:
                    self.hist_add_ai_message(response)
                    return response
                
                for tool_call in tool_calls:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("args", {})
                    
                    tool_response = await self.execute_tool(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        message=response,
                        loop_data=loop_data,
                    )
                    
                    if tool_response.break_loop:
                        return tool_response.message
                    
                    messages = self.history.get_messages_for_llm()
                
            except RepairableException as e:
                self.hist_add_tool_result("error", str(e))
                messages = self.history.get_messages_for_llm()
    
    async def execute_tool(
        self, tool_name: str, tool_args: Dict[str, Any], message: str, loop_data: LoopData
    ) -> Response:
        # First try to find the tool in the local tools
        tool_instance = await self.find_local_tool(tool_name, tool_args, message, loop_data)
        
        # If not found locally, try MCP
        if not tool_instance:
            try:
                from helpers.mcp_handler import MCPHandler
                mcp_handler = MCPHandler(self)
                tool_instance = await mcp_handler.find_tool(tool_name, tool_args, message, loop_data)
            except Exception:
                # If MCP fails, continue with local tools only
                pass
        
        if not tool_instance:
            return Response(
                message=f"Tool '{tool_name}' not found. Please use one of the available tools.",
                break_loop=False,
            )
        
        # Execute the tool
        await tool_instance.before_execution()
        response = await tool_instance.execute()
        await tool_instance.after_execution(response)
        
        return response

    async def find_local_tool(
        self, tool_name: str, tool_args: Dict[str, Any], message: str, loop_data: LoopData
    ) -> Tool | None:
        # Load tools from the tools directory
        tools_dir = files.get_abs_path("tools")
        tool_classes = extract_tools.load_classes_from_folder(tools_dir, "*", Tool)
        
        # Check if any tool matches the requested name
        for tool_class in tool_classes:
            if tool_class.__name__.lower() == tool_name.lower():
                return tool_class(
                    agent=self,
                    name=tool_name,
                    method=None,
                    args=tool_args,
                    message=message,
                    loop_data=loop_data,
                )
        
        return None

    async def stream_callback(self, chunk: str):
        await self.call_extensions("stream_callback", chunk=chunk)

    def handle_critical_exception(self, e: Exception):
        import traceback
        print(f"Critical exception in {self.agent_name}: {str(e)}")
        print(traceback.format_exc())