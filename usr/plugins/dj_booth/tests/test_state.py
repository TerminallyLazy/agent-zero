import asyncio
import pytest
from usr.plugins.dj_booth.helpers.state import (
    StreamState, get_state, get_lifecycle_lock, reset_state,
)


def test_get_state_returns_singleton():
    s1 = get_state()
    s2 = get_state()
    assert s1 is s2


def test_default_state_values():
    reset_state()
    s = get_state()
    assert s.is_running is False
    assert s.engine == ""
    assert s.listener_count == 0
    assert s.queue == []
    assert s.error == ""


def test_lifecycle_lock_is_singleton():
    l1 = get_lifecycle_lock()
    l2 = get_lifecycle_lock()
    assert l1 is l2
    assert isinstance(l1, asyncio.Lock)


def test_reset_state_clears_runtime_fields_keeps_library_count():
    reset_state()
    s = get_state()
    s.is_running = True
    s.listener_count = 5
    s.library_count = 42
    s.error = "old"
    reset_state(keep_library=True, keep_error=False)
    s = get_state()
    assert s.is_running is False
    assert s.listener_count == 0
    assert s.library_count == 42
    assert s.error == ""
