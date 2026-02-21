import threading
from typing import Any

_lock = threading.RLock()
_cache: dict[str, dict[str, Any]] = {}


def add(area: str, key: str, data: Any) -> None:
    with _lock:
        if area not in _cache:
            _cache[area] = {}
        _cache[area][key] = data


def get(area: str, key: str, default: Any = None) -> Any:
    with _lock:
        return _cache.get(area, {}).get(key, default)


def remove(area: str, key: str) -> None:
    with _lock:
        if area in _cache:
            _cache[area].pop(key, None)


def clear(area: str) -> None:
    with _lock:
        _cache.pop(area, None)


def clear_all() -> None:
    with _lock:
        _cache.clear()
