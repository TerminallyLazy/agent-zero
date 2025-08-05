import os
from typing import Optional

# Try to import from python_dotenv or python-dotenv
try:
    from python_dotenv import load_dotenv as _load_dotenv
except ImportError:
    from dotenv import load_dotenv as _load_dotenv


def load_dotenv():
    """Load environment variables from .env file."""
    # Look for .env in the current directory and parent directories
    _load_dotenv()
    
    # Also look for .env in the application directory
    from helpers.files import get_base_dir
    env_path = os.path.join(get_base_dir(), ".env")
    if os.path.exists(env_path):
        _load_dotenv(env_path)


def get_dotenv_value(key: str) -> Optional[str]:
    """Get an environment variable value."""
    return os.environ.get(key)