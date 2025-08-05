import importlib
import inspect
import os
import re
import glob
from typing import Dict, List, Any, Type, TypeVar

T = TypeVar('T')


def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Extract tool calls from a text string.
    
    Supports both JSON and function call formats:
    - JSON: {"name": "tool_name", "args": {"arg1": "value1"}}
    - Function call: tool_name(arg1="value1", arg2="value2")
    """
    tools = []
    
    # Try to extract JSON-formatted tool calls
    json_pattern = r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"args"\s*:\s*(\{[^}]+\})\s*\}'
    json_matches = re.finditer(json_pattern, text, re.DOTALL)
    
    for match in json_matches:
        try:
            tool_name = match.group(1)
            args_str = match.group(2)
            
            # Simple JSON parsing for args
            args = {}
            arg_pattern = r'"([^"]+)"\s*:\s*"([^"]*)"'
            for arg_match in re.finditer(arg_pattern, args_str):
                arg_name = arg_match.group(1)
                arg_value = arg_match.group(2)
                args[arg_name] = arg_value
            
            tools.append({"name": tool_name, "args": args})
        except Exception:
            continue
    
    # If no JSON tools found, try function call format
    if not tools:
        func_pattern = r'(\w+)\s*\(\s*(.*?)\s*\)'
        func_matches = re.finditer(func_pattern, text)
        
        for match in func_matches:
            try:
                tool_name = match.group(1)
                args_str = match.group(2)
                
                # Parse args
                args = {}
                arg_pattern = r'(\w+)\s*=\s*"([^"]*)"'
                for arg_match in re.finditer(arg_pattern, args_str):
                    arg_name = arg_match.group(1)
                    arg_value = arg_match.group(2)
                    args[arg_name] = arg_value
                
                tools.append({"name": tool_name, "args": args})
            except Exception:
                continue
    
    return tools


def load_classes_from_folder(folder_path: str, pattern: str, base_class: Type[T]) -> List[Type[T]]:
    """
    Load all classes from Python files in a folder that inherit from a base class.
    
    Args:
        folder_path: Path to the folder containing Python files
        pattern: Glob pattern for files to load
        base_class: Base class that loaded classes should inherit from
    
    Returns:
        List of class types that inherit from the base class
    """
    classes = []
    
    if not os.path.exists(folder_path):
        return classes
    
    # Get all Python files matching the pattern
    file_pattern = os.path.join(folder_path, f"{pattern}.py")
    py_files = glob.glob(file_pattern)
    
    for file_path in py_files:
        try:
            # Convert file path to module path
            rel_path = os.path.relpath(file_path, os.path.dirname(folder_path))
            module_name = os.path.splitext(rel_path)[0].replace(os.path.sep, '.')
            
            # Import the module
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find all classes in the module that inherit from the base class
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, base_class) and obj != base_class:
                        classes.append(obj)
        except Exception as e:
            print(f"Error loading module {file_path}: {str(e)}")
    
    return classes