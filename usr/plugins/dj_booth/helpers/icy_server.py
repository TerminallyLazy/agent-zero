"""Pure-Python ICY-compatible streaming server.

Drop-in replacement for icecast2 when icecast2 isn't available (e.g. Kali
base image where it isn't in the default repos). Same wire protocol —
listeners using VLC, Winamp, foobar2000, browsers all work.

Architecture:
- asyncio.start_server listens on configured port
- GET <mount>      → infinite mp3 stream (ICY response headers)
- GET /status-json.xsl → icecast-compatible JSON status (drives our listener-count poll)
- push_chunk(bytes)    → called by engine to feed audio bytes into the broadcast

Slow listeners get dropped on queue overflow rather than blocking the source.
Stdlib only — no aiohttp, no third-party deps.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, Set


log = logging.getLogger(__name__)

LISTENER_QUEUE_SIZE = 32
SOURCE_QUEUE_SIZE = 200


class IcyServer:
    """In-process ICY/HTTP streaming server."""

    def __init__(self, port: int, mount: str, stream_name: str = "Stream",
                 stream_description: str = "", stream_genre: str = ""):
        self.port = int(port)
        self.mount = mount or "/stream"
        self.stream_name = stream_name
        self.stream_description = stream_description
        self.stream_genre = stream_genre

        self._listeners: Set[asyncio.Queue] = set()
        self._source_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=SOURCE_QUEUE_SIZE)
        self._server: Optional[asyncio.AbstractServer] = None
        self._broadcast_task: Optional[asyncio.Task] = None
        self._current_track: str = ""
        self._running: bool = False

    @property
    def listener_count(self) -> int:
        return len(self._listeners)

    @property
    def is_running(self) -> bool:
        return self._running

    def set_current_track(self, display: str) -> None:
        """Update icy-meta-data shown to listener clients on the next chunk."""
        self._current_track = display or ""

    async def start(self) -> None:
        if self._running:
            return
        self._server = await asyncio.start_server(
            self._handle_client, "0.0.0.0", self.port,
        )
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        self._running = True
        log.info("dj_booth IcyServer listening on :%d%s", self.port, self.mount)

    async def stop(self) -> None:
        self._running = False
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            self._broadcast_task = None
        if self._server:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
        # Drain any pending listener queues so connected clients drop cleanly
        for q in list(self._listeners):
            try:
                q.put_nowait(b"")
            except Exception:
                pass
        self._listeners.clear()

    async def push_chunk(self, data: bytes) -> None:
        if not data or not self._running:
            return
        try:
            self._source_queue.put_nowait(data)
        except asyncio.QueueFull:
            # Drop oldest to keep up — bias toward latest audio
            try:
                self._source_queue.get_nowait()
                self._source_queue.put_nowait(data)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    async def _broadcast_loop(self) -> None:
        try:
            while True:
                chunk = await self._source_queue.get()
                if not chunk:
                    continue
                dead: Set[asyncio.Queue] = set()
                for q in self._listeners:
                    try:
                        q.put_nowait(chunk)
                    except asyncio.QueueFull:
                        dead.add(q)
                if dead:
                    self._listeners -= dead
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("dj_booth IcyServer broadcast loop error")

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername") or ("?", "?")
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not request_line:
                return
            request = request_line.decode(errors="replace").strip()
            # Drain headers
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=10.0)
                if not line or line in (b"\r\n", b"\n"):
                    break

            parts = request.split(maxsplit=2)
            if len(parts) < 2:
                writer.write(b"HTTP/1.0 400 Bad Request\r\n\r\n")
                await writer.drain()
                return
            method, path = parts[0].upper(), parts[1]

            if path.startswith("/status-json.xsl") or path.startswith("/admin/stats"):
                await self._serve_status(writer)
                return

            if path == "/" or path == "/status.xsl":
                await self._serve_status_html(writer)
                return

            if path != self.mount:
                writer.write(b"HTTP/1.0 404 Not Found\r\n"
                             b"Content-Type: text/plain\r\n\r\n"
                             b"mount not found\n")
                await writer.drain()
                return

            await self._serve_stream(writer, peer)
        except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            log.exception("dj_booth IcyServer client handler error")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _serve_status(self, writer: asyncio.StreamWriter) -> None:
        body = json.dumps({
            "icestats": {
                "source": {
                    "listenurl": f"http://localhost:{self.port}{self.mount}",
                    "listeners": self.listener_count,
                    "stream_name": self.stream_name,
                    "stream_description": self.stream_description,
                    "genre": self.stream_genre,
                    "title": self._current_track,
                    "server_type": "audio/mpeg",
                }
            }
        })
        body_bytes = body.encode()
        headers = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        writer.write(headers + body_bytes)
        await writer.drain()

    async def _serve_status_html(self, writer: asyncio.StreamWriter) -> None:
        html = f"""<!doctype html>
<html><head><title>{self.stream_name}</title></head>
<body style="font-family:system-ui;padding:2rem;background:#1a1a2e;color:#e8e8f0">
<h1>🎧 {self.stream_name}</h1>
<p>{self.stream_description or 'Powered by Agent Zero DJ Booth.'}</p>
<p><b>Listen:</b> <code>http://&lt;host&gt;:{self.port}{self.mount}</code></p>
<p><b>Now playing:</b> {self._current_track or '(silence)'}</p>
<p><b>Listeners:</b> {self.listener_count}</p>
<p><audio controls src="{self.mount}" style="width:100%"></audio></p>
</body></html>
"""
        body_bytes = html.encode()
        headers = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        writer.write(headers + body_bytes)
        await writer.drain()

    async def _serve_stream(self, writer: asyncio.StreamWriter, peer) -> None:
        # ICY-compatible response headers
        headers = (
            "ICY 200 OK\r\n"
            f"icy-name: {self.stream_name}\r\n"
            f"icy-description: {self.stream_description}\r\n"
            f"icy-genre: {self.stream_genre}\r\n"
            "icy-pub: 0\r\n"
            "icy-br: 192\r\n"
            "Content-Type: audio/mpeg\r\n"
            "Cache-Control: no-cache\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        writer.write(headers.encode())
        await writer.drain()

        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=LISTENER_QUEUE_SIZE)
        self._listeners.add(q)
        log.info("dj_booth IcyServer: listener +1 from %s (total=%d)", peer, self.listener_count)
        try:
            while True:
                chunk = await q.get()
                if not chunk:
                    return  # shutdown signal
                writer.write(chunk)
                try:
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError):
                    return
        finally:
            self._listeners.discard(q)
            log.info("dj_booth IcyServer: listener -1 from %s (total=%d)", peer, self.listener_count)
