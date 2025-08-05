from dataclasses import dataclass, field
from enum import Enum
import logging
import os
from typing import Any, Awaitable, Callable, List, Optional, Dict, AsyncIterator

from litellm import completion, acompletion, embedding
import litellm

from helpers import dotenv
from helpers.tokens import approximate_tokens

from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.outputs.chat_generation import ChatGenerationChunk
from langchain_core.callbacks.manager import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage, AIMessageChunk, HumanMessage, SystemMessage


# disable extra logging
def turn_off_logging():
    os.environ["LITELLM_LOG"] = "ERROR"  # only errors
    litellm.suppress_debug_info = True
    # Silence **all** LiteLLM sub-loggers
    for name in logging.Logger.manager.loggerDict:
        if name.lower().startswith("litellm"):
            logging.getLogger(name).setLevel(logging.ERROR)


# init
dotenv.load_dotenv()
turn_off_logging()


class ModelType(Enum):
    CHAT = "Chat"
    UTILITY = "Utility"


@dataclass
class ModelConfig:
    type: ModelType
    provider: str
    name: str
    api_base: str = ""
    ctx_length: int = 0
    limit_requests: int = 0
    limit_input: int = 0
    limit_output: int = 0
    vision: bool = False
    kwargs: dict = field(default_factory=dict)

    def build_kwargs(self):
        kwargs = self.kwargs.copy() or {}
        if self.api_base and "api_base" not in kwargs:
            kwargs["api_base"] = self.api_base
        return kwargs


def get_api_key(service: str) -> str:
    return (
        dotenv.get_dotenv_value(f"API_KEY_{service.upper()}")
        or dotenv.get_dotenv_value(f"{service.upper()}_API_KEY")
        or dotenv.get_dotenv_value(f"{service.upper()}_API_TOKEN")
        or "None"
    )


async def chat_completion(
    model: ModelConfig,
    system_prompt: str,
    messages: List[Dict[str, str]],
    stream: bool = False,
    callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> str:
    """
    Send a chat completion request to the model.
    """
    turn_off_logging()
    
    # Prepare the messages
    formatted_messages = []
    if system_prompt:
        formatted_messages.append({"role": "system", "content": system_prompt})
    
    for msg in messages:
        formatted_messages.append(msg)
    
    # Build the kwargs
    kwargs = model.build_kwargs()
    
    # Add the API key
    api_key = get_api_key(model.provider)
    if api_key != "None":
        kwargs["api_key"] = api_key
    
    if stream:
        response_text = ""
        async for chunk in _stream_chat_completion(model, formatted_messages, kwargs):
            if callback:
                await callback(chunk)
            response_text += chunk
        return response_text
    else:
        response = await acompletion(
            model=f"{model.provider}/{model.name}",
            messages=formatted_messages,
            **kwargs
        )
        return response.choices[0].message.content or ""


async def _stream_chat_completion(
    model: ModelConfig, messages: List[Dict[str, str]], kwargs: Dict[str, Any]
) -> AsyncIterator[str]:
    """
    Stream a chat completion request to the model.
    """
    response = await acompletion(
        model=f"{model.provider}/{model.name}",
        messages=messages,
        stream=True,
        **kwargs
    )
    
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


class LiteLLMChatModel(SimpleChatModel):
    """LangChain compatible chat model using LiteLLM."""
    
    model_config: ModelConfig
    
    def __init__(self, model_config: ModelConfig):
        super().__init__()
        self.model_config = model_config
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatGenerationChunk:
        """Generate a chat response."""
        formatted_messages = []
        
        for message in messages:
            if isinstance(message, SystemMessage):
                formatted_messages.append({"role": "system", "content": message.content})
            elif isinstance(message, HumanMessage):
                formatted_messages.append({"role": "user", "content": message.content})
            else:
                formatted_messages.append({"role": "assistant", "content": message.content})
        
        model_kwargs = self.model_config.build_kwargs()
        if stop:
            model_kwargs["stop"] = stop
        
        api_key = get_api_key(self.model_config.provider)
        if api_key != "None":
            model_kwargs["api_key"] = api_key
        
        response = await acompletion(
            model=f"{self.model_config.provider}/{self.model_config.name}",
            messages=formatted_messages,
            **model_kwargs
        )
        
        return ChatGenerationChunk(
            message=AIMessageChunk(content=response.choices[0].message.content or ""),
            generation_info={"model_name": f"{self.model_config.provider}/{self.model_config.name}"}
        )
    
    @property
    def _llm_type(self) -> str:
        return "litellm-chat"