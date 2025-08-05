from abc import abstractmethod
from typing import Any, List, Type
from helpers import files, extract_tools


class Extension:
    def __init__(self, agent: Any = None, **kwargs):
        self.agent = agent
        self.kwargs = kwargs

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass


async def call_extensions(extension_point: str, agent: Any = None, **kwargs) -> Any:
    """
    Call all extensions for a given extension point.
    
    Args:
        extension_point: The name of the extension point
        agent: The agent instance
        **kwargs: Additional arguments to pass to the extensions
    """
    # Get default extensions
    extensions_dir = files.get_abs_path("extensions", extension_point)
    classes = await _get_extensions(extensions_dir)
    
    # Get agent-specific extensions if available
    if agent and agent.config.profile:
        agent_extensions_dir = files.get_abs_path("agents", agent.config.profile, "extensions", extension_point)
        agent_classes = await _get_extensions(agent_extensions_dir)
        
        if agent_classes:
            # Merge extensions, with agent-specific ones taking precedence
            unique = {}
            for cls in classes + agent_classes:
                unique[_get_file_from_module(cls.__module__)] = cls
            
            # Sort by name
            classes = sorted(unique.values(), key=lambda cls: _get_file_from_module(cls.__module__))
    
    # Call all extensions
    for cls in classes:
        await cls(agent=agent).execute(**kwargs)


def _get_file_from_module(module_name: str) -> str:
    """Get the file name from a module name."""
    return module_name.split(".")[-1]


# Cache for loaded extensions
_cache: dict[str, List[Type[Extension]]] = {}


async def _get_extensions(folder: str) -> List[Type[Extension]]:
    """
    Get all extensions from a folder.
    
    Args:
        folder: Path to the folder containing extension files
    
    Returns:
        List of extension classes
    """
    global _cache
    
    if folder in _cache:
        return _cache[folder]
    
    if not files.exists(folder):
        return []
    
    classes = extract_tools.load_classes_from_folder(folder, "*", Extension)
    _cache[folder] = classes
    
    return classes