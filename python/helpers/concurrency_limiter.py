import asyncio
from typing import Dict, Any, AsyncContextManager
from contextlib import asynccontextmanager
import logging


class ConcurrencyLimiter:
    """
    Manages concurrent access to resources using asyncio.Semaphore.
    Provides per-provider/per-key concurrency limiting for LLM calls and agent communications.
    
    Based on Agent Zero's existing rate limiting patterns, this class provides
    thread-safe semaphore management for concurrent operations.
    """
    
    _instances: Dict[str, 'ConcurrencyLimiter'] = {}
    _locks: Dict[str, asyncio.Semaphore] = {}
    _lock = asyncio.Lock()
    
    def __init__(self, max_concurrent: int = 5):
        """
        Initialize a ConcurrencyLimiter with a maximum concurrent operation limit.
        
        Args:
            max_concurrent: Maximum number of concurrent operations allowed
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_count = 0
        self._wait_count = 0
    
    @classmethod
    async def get_limiter(cls, key: str, max_concurrent: int = 5) -> 'ConcurrencyLimiter':
        """
        Get or create a ConcurrencyLimiter instance for a specific key.
        
        Args:
            key: Unique identifier for the resource (e.g., provider name)
            max_concurrent: Maximum concurrent operations for this key
            
        Returns:
            ConcurrencyLimiter instance for the specified key
        """
        async with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(max_concurrent)
            return cls._instances[key]
    
    @classmethod
    @asynccontextmanager
    async def guard(cls, key: str, max_concurrent: int = 5) -> AsyncContextManager[None]:
        """
        Context manager for guarding concurrent access to a resource.
        
        Args:
            key: Unique identifier for the resource
            max_concurrent: Maximum concurrent operations allowed
            
        Usage:
            async with ConcurrencyLimiter.guard("openai", 10):
                # Your concurrent operation here
                result = await some_async_operation()
        """
        limiter = await cls.get_limiter(key, max_concurrent)
        async with limiter.acquire():
            yield
    
    @asynccontextmanager
    async def acquire(self) -> AsyncContextManager[None]:
        """
        Acquire a semaphore slot for concurrent operation.
        
        Provides detailed logging and statistics about concurrent operations.
        """
        self._wait_count += 1
        
        try:
            # Log when we're waiting for a slot
            if self._active_count >= self.max_concurrent:
                logging.debug(f"Waiting for concurrency slot ({self._active_count}/{self.max_concurrent} active, {self._wait_count} waiting)")
            
            async with self._semaphore:
                self._wait_count -= 1
                self._active_count += 1
                
                try:
                    logging.debug(f"Acquired concurrency slot ({self._active_count}/{self.max_concurrent} active)")
                    yield
                finally:
                    self._active_count -= 1
                    logging.debug(f"Released concurrency slot ({self._active_count}/{self.max_concurrent} active)")
        
        except Exception:
            self._wait_count -= 1
            raise
    
    @property
    def active_count(self) -> int:
        """Current number of active concurrent operations."""
        return self._active_count
    
    @property
    def waiting_count(self) -> int:
        """Current number of operations waiting for a slot."""
        return self._wait_count
    
    @property
    def available_count(self) -> int:
        """Number of available slots for new operations."""
        return self.max_concurrent - self._active_count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get current statistics about concurrency usage.
        
        Returns:
            Dictionary containing active, waiting, available, and max concurrent counts
        """
        return {
            "active": self._active_count,
            "waiting": self._wait_count,
            "available": self.available_count,
            "max_concurrent": self.max_concurrent
        }
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all active ConcurrencyLimiter instances.
        
        Returns:
            Dictionary mapping keys to their concurrency statistics
        """
        return {key: limiter.get_stats() for key, limiter in cls._instances.items()}
    
    @classmethod
    async def reset_all(cls):
        """Reset all ConcurrencyLimiter instances. Useful for testing."""
        async with cls._lock:
            cls._instances.clear()
            cls._locks.clear()


# Convenience function for common usage patterns
async def with_concurrency_limit(key: str, max_concurrent: int = 5):
    """
    Convenience function that returns a context manager for concurrency limiting.
    
    Args:
        key: Unique identifier for the resource
        max_concurrent: Maximum concurrent operations allowed
        
    Returns:
        Async context manager for concurrency limiting
    """
    return ConcurrencyLimiter.guard(key, max_concurrent)