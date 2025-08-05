import os
import re
from typing import List, Dict, Any, Optional


def get_base_dir() -> str:
    """Get the base directory of the application."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_abs_path(*paths) -> str:
    """Get an absolute path relative to the base directory."""
    return os.path.abspath(os.path.join(get_base_dir(), *paths))


def exists(path: str) -> bool:
    """Check if a file or directory exists."""
    return os.path.exists(path)


def read_file(path: str) -> str:
    """Read a file and return its contents."""
    if not exists(path):
        return ""
    
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> bool:
    """Write content to a file."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False


def read_prompt_file(path: str, _backup_dirs: List[str] = None, **kwargs) -> str:
    """
    Read a prompt file and substitute variables.
    
    Args:
        path: Path to the prompt file
        _backup_dirs: List of backup directories to look for the file
        **kwargs: Variables to substitute in the prompt
    """
    content = ""
    
    # Try to read from the primary path
    if exists(path):
        content = read_file(path)
    
    # If not found and backup dirs are provided, try them
    if not content and _backup_dirs:
        for backup_dir in _backup_dirs:
            backup_path = os.path.join(backup_dir, os.path.basename(path))
            if exists(backup_path):
                content = read_file(backup_path)
                break
    
    # Substitute variables
    if content and kwargs:
        for key, value in kwargs.items():
            content = content.replace(f"{{{key}}}", str(value))
    
    return content


def remove_code_fences(text: str) -> str:
    """Remove Markdown code fences from text."""
    # Remove triple backtick blocks
    text = re.sub(r'```[^\n]*\n[\s\S]*?```', '', text)
    
    # Remove single backtick blocks
    text = re.sub(r'`[^`]*`', '', text)
    
    return text