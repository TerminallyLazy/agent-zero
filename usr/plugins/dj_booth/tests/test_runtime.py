import asyncio
import pytest

from usr.plugins.dj_booth.helpers import runtime as rt


@pytest.fixture(autouse=True)
def _reset_runtime():
    yield
    rt.shutdown()


def test_get_loop_returns_running_loop():
    loop = rt.get_loop()
    assert loop is not None
    assert not loop.is_closed()


def test_run_sync_returns_result_of_coroutine():
    async def add(a, b):
        await asyncio.sleep(0.01)
        return a + b

    assert rt.run_sync(add(2, 3), timeout=2.0) == 5


def test_submit_returns_concurrent_future():
    async def mul(a, b):
        return a * b

    fut = rt.submit(mul(4, 5))
    assert fut.result(timeout=2.0) == 20


def test_runtime_survives_multiple_calls():
    async def echo(x):
        return x

    for i in range(5):
        assert rt.run_sync(echo(i), timeout=2.0) == i


def test_run_sync_propagates_exceptions():
    async def bad():
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        rt.run_sync(bad(), timeout=2.0)


@pytest.mark.asyncio
async def test_run_async_from_another_loop():
    async def add(a, b):
        await asyncio.sleep(0.01)
        return a + b

    # Calling from this asyncio test loop, scheduled onto the runtime loop
    result = await rt.run_async(add(7, 8), timeout=2.0)
    assert result == 15


def test_runtime_loop_is_persistent():
    """Same loop returned across calls — that's the whole point of this module."""
    loop1 = rt.get_loop()
    rt.run_sync(asyncio.sleep(0))
    loop2 = rt.get_loop()
    assert loop1 is loop2
