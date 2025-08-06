from agent import AgentConfig
import models
from python.helpers import runtime, settings, defer
from python.helpers.print_style import PrintStyle


def initialize_agent():
    current_settings = settings.get_settings()

    def _normalize_model_kwargs(kwargs: dict) -> dict:
        # convert string values that represent valid Python numbers to numeric types
        result = {}
        for key, value in kwargs.items():
            if isinstance(value, str):
                # try to convert string to number if it's a valid Python number
                try:
                    # try int first, then float
                    result[key] = int(value)
                except ValueError:
                    try:
                        result[key] = float(value)
                    except ValueError:
                        result[key] = value
            else:
                result[key] = value
        return result

    # chat model from user settings - FULL LiteLLM support
    chat_llm = models.ModelConfig(
        type=models.ModelType.CHAT,
        provider=current_settings["chat_model_provider"],
        name=current_settings["chat_model_name"],
        api_base=current_settings["chat_model_api_base"],
        ctx_length=current_settings["chat_model_ctx_length"],
        vision=current_settings["chat_model_vision"],
        limit_requests=current_settings["chat_model_rl_requests"],
        limit_input=current_settings["chat_model_rl_input"],
        limit_output=current_settings["chat_model_rl_output"],
        kwargs=_normalize_model_kwargs(current_settings["chat_model_kwargs"]),
    )

    # utility model from user settings - FULL LiteLLM support
    utility_llm = models.ModelConfig(
        type=models.ModelType.CHAT,
        provider=current_settings["util_model_provider"],
        name=current_settings["util_model_name"],
        api_base=current_settings["util_model_api_base"],
        ctx_length=current_settings["util_model_ctx_length"],
        limit_requests=current_settings["util_model_rl_requests"],
        limit_input=current_settings["util_model_rl_input"],
        limit_output=current_settings["util_model_rl_output"],
        kwargs=_normalize_model_kwargs(current_settings["util_model_kwargs"]),
    )

    # browser model from user settings - Keep for API compatibility
    browser_llm = models.ModelConfig(
        type=models.ModelType.CHAT,
        provider=current_settings["browser_model_provider"],
        name=current_settings["browser_model_name"],
        api_base=current_settings["browser_model_api_base"],
        ctx_length=current_settings["browser_model_ctx_length"],
        vision=current_settings["browser_model_vision"],
        limit_requests=current_settings["browser_model_rl_requests"],
        limit_input=current_settings["browser_model_rl_input"],
        limit_output=current_settings["browser_model_rl_output"],
        kwargs=_normalize_model_kwargs(current_settings["browser_model_kwargs"]),
    )

    # embeddings model from user settings
    embeddings_llm = models.ModelConfig(
        type=models.ModelType.EMBEDDING,
        provider=current_settings["embed_model_provider"],
        name=current_settings["embed_model_name"],
        api_base=current_settings["embed_model_api_base"],
        limit_requests=current_settings["embed_model_rl_requests"],
        limit_input=current_settings["embed_model_rl_input"],
        kwargs=_normalize_model_kwargs(current_settings["embed_model_kwargs"]),
    )

    # initialize agent with simplified config (no Docker/SSH)
    agent_config = AgentConfig(
        chat_model=chat_llm,
        utility_model=utility_llm,
        browser_model=browser_llm,  # Keep for compatibility
        embeddings_model=embeddings_llm,
        mcp_servers=current_settings.get("mcp_servers", "{}"),
        code_exec_local=True,  # Always local execution
        memory_subdir=current_settings["agent_memory_subdir"],
        knowledge_subdirs=current_settings.get("knowledge_subdirs", ["default", "custom"]),
    )

    # Print configuration info
    PrintStyle(font_color="green", bold=True).print(
        f"Agent Zero Lite initialized with:"
    )
    PrintStyle(font_color="cyan").print(
        f"  Chat Model: {chat_llm.provider}/{chat_llm.name}"
    )
    PrintStyle(font_color="cyan").print(
        f"  Utility Model: {utility_llm.provider}/{utility_llm.name}"
    )
    PrintStyle(font_color="cyan").print(
        f"  Embeddings: {embeddings_llm.provider}/{embeddings_llm.name}"
    )
    
    # Initialize MCP if configured
    mcp_servers = current_settings.get("mcp_servers", "{}")
    if mcp_servers and mcp_servers != "{}":
        try:
            from python.helpers import mcp_handler
            mcp_handler.initialize_mcp(mcp_servers)
            PrintStyle(font_color="cyan").print(f"  MCP Servers: Configured")
        except Exception as e:
            PrintStyle(font_color="yellow").print(f"  MCP Servers: Not available ({e})")
    
    return agent_config