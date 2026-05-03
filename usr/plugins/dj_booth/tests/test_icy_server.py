import asyncio
import pytest

from usr.plugins.dj_booth.helpers.icy_server import IcyServer


@pytest.mark.asyncio
async def test_icy_server_starts_and_stops_cleanly():
    s = IcyServer(port=0, mount="/stream", stream_name="t")
    # port=0 is not allowed by start_server with our usage, so start with a real port
    s.port = 19999
    await s.start()
    assert s.is_running
    await s.stop()
    assert not s.is_running


@pytest.mark.asyncio
async def test_icy_server_push_chunk_no_listeners_doesnt_block():
    s = IcyServer(port=19998, mount="/stream", stream_name="t")
    await s.start()
    try:
        for _ in range(50):
            await s.push_chunk(b"\x00" * 256)
        # Broadcast loop should drain into the (empty) listener set without raising
        await asyncio.sleep(0.05)
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_icy_server_status_endpoint_returns_listener_count():
    s = IcyServer(port=19997, mount="/stream", stream_name="MyStation",
                  stream_description="desc", stream_genre="Test")
    await s.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 19997)
        writer.write(b"GET /status-json.xsl HTTP/1.0\r\n\r\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        text = data.decode(errors="replace")
        assert "200 OK" in text
        assert "MyStation" in text
        assert '"listeners": 0' in text
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_icy_server_set_current_track_reflects_in_status():
    s = IcyServer(port=19996, mount="/stream", stream_name="t")
    await s.start()
    try:
        s.set_current_track("Artist - Title")
        reader, writer = await asyncio.open_connection("127.0.0.1", 19996)
        writer.write(b"GET /status-json.xsl HTTP/1.0\r\n\r\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
        writer.close()
        assert b"Artist - Title" in data
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_icy_server_unknown_path_returns_404():
    s = IcyServer(port=19995, mount="/stream", stream_name="t")
    await s.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 19995)
        writer.write(b"GET /nonsense HTTP/1.0\r\n\r\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(1024), timeout=2.0)
        writer.close()
        assert b"404" in data
    finally:
        await s.stop()
