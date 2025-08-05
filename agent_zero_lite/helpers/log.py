import logging
from typing import Dict, Any, Optional


class LogItem:
    def __init__(self, type: str, heading: str, content: str = "", kvps: Dict[str, Any] = None):
        self.type = type
        self.heading = heading
        self.content = content
        self.kvps = kvps or {}
        self.finished = False
    
    def update(self, content: Optional[str] = None, finished: bool = False):
        if content is not None:
            self.content = content
        self.finished = finished


class Log:
    def __init__(self):
        self.items = []
        self.logger = self._setup_logger()
    
    def _setup_logger(self):
        logger = logging.getLogger("agent_zero_lite")
        logger.setLevel(logging.INFO)
        
        # Create console handler if not already added
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def log(self, type: str, heading: str, content: str = "", kvps: Dict[str, Any] = None) -> LogItem:
        """
        Log an item and return it for future updates.
        """
        item = LogItem(type, heading, content, kvps)
        self.items.append(item)
        
        # Also log to the Python logger
        self.logger.info(f"{heading}: {content}")
        
        return item