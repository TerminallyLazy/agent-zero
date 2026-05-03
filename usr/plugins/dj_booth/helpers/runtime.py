"""Persistent asyncio runtime for the dj_booth plugin.

Why this exists: Flask 3 with [async] runs each async view in a fresh,
short-lived event loop. Tasks created with asyncio.create_task inside a
view get cancelled the moment the view returns. That kills the IcyServer,
the ffmpeg engine loop, the health loop, and the tunnel runner — even
though the API handler reports success.

Solution: own a single asyncio event loop in a daemon thread that lives
for the lifetime of the A0 process. Every long-running coroutine in this
plugin runs on THAT loop. Flask handlers use submit() / run_sync() to
schedule work onto it without blocking their own loop.

Usage:
    from usr.plugins.dj_booth.helpers.runtime import run_sync, get_loop

    # From an async Flask handler:
    await asyncio.wrap_future(submit(lifecycle.start_stack(cfg)))

    # From a sync context:
    run_sync(lifecycle.start_stack(cfg), timeout=30.0)
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any, Coroutine, Optional, TypeVar


log = logging.getLogger(__name__)

T = TypeVar("T")

_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()


def _ensure_running() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _loop is not None and _thread is not None and _thread.is_alive() and not _loop.is_closed():
            return _loop

        loop = asyncio.new_event_loop()

        def _runner():
            asyncio.set_event_loop(loop)
            try:
                loop.run_forever()
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        thread = threading.Thread(target=_runner, daemon=True, name="dj_booth-runtime")
        thread.start()
        _loop = loop
        _thread = thread
        log.info("dj_booth runtime: started persistent asyncio loop")
        return loop


def get_loop() -> asyncio.AbstractEventLoop:
    return _ensure_running()


def submit(coro: Coroutine[Any, Any, T]) -> "Future[T]":
    """Schedule coro on the runtime loop. Returns a concurrent.futures.Future."""
    loop = _ensure_running()
    return asyncio.run_coroutine_threadsafe(coro, loop)


def run_sync(coro: Coroutine[Any, Any, T], timeout: Optional[float] = None) -> T:
    """Schedule + wait. Call from any context."""
    return submit(coro).result(timeout=timeout)


async def run_async(coro: Coroutine[Any, Any, T], timeout: Optional[float] = None) -> T:
    """Schedule on runtime + await from another asyncio loop (e.g. Flask request loop)."""
    fut = submit(coro)
    return await asyncio.wait_for(asyncio.wrap_future(fut), timeout=timeout)


def shutdown() -> None:
    """Best-effort: stop the runtime loop. Used by tests; not normally called."""
    global _loop, _thread
    with _lock:
        if _loop is not None and not _loop.is_closed():
            try:
                _loop.call_soon_threadsafe(_loop.stop)
            except Exception:
                pass
        if _thread is not None:
            _thread.join(timeout=2.0)
        _loop = None
        _thread = None
