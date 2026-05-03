"""StreamEngine: protocol + FfmpegEngine (fallback) + LiquidsoapEngine (preferred).

Engine selection is one-shot at start() — no mid-session auto-swap.
See spec section 4.4 for failure semantics.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Optional, Protocol


log = logging.getLogger(__name__)


LIQ_TELNET_HOST = "localhost"
LIQ_TELNET_PORT = 1234
LIQ_SCRIPT_PATH = "/tmp/dj_booth.liq"


LIQ_SCRIPT_TEMPLATE = '''# dj_booth — generated, do not edit
set("server.telnet", true)
set("server.telnet.port", {telnet_port})
set("log.file", false)
set("log.stdout", true)

queue = request.queue(id="main")
source = audio_to_stereo(queue)
source = mksafe(source)

output.icecast(
  %mp3(bitrate={bitrate}),
  host="localhost",
  port={icecast_port},
  password="{source_password}",
  mount="{mount}",
  name="{stream_name}",
  description="{stream_description}",
  genre="{stream_genre}",
  url="{stream_url}",
  public={public_int},
  source
)
'''


def render_liq_script(cfg: dict) -> str:
    return LIQ_SCRIPT_TEMPLATE.format(
        telnet_port=LIQ_TELNET_PORT,
        bitrate=int(cfg.get("bitrate", 192)),
        icecast_port=int(cfg["icecast_port"]),
        source_password=cfg["icecast_source_password"],
        mount=cfg.get("mount", "/stream"),
        stream_name=cfg.get("stream_name", "Stream"),
        stream_description=cfg.get("stream_description", ""),
        stream_genre=cfg.get("stream_genre", ""),
        stream_url=cfg.get("stream_url", ""),
        public_int="true" if cfg.get("public_listing") else "false",
    )


class StreamEngine(Protocol):
    name: str
    async def start(self, config: dict, initial_tracks: list[str]) -> None: ...
    async def stop(self) -> None: ...
    async def queue_track(self, path: str) -> None: ...
    async def skip(self) -> None: ...
    async def clear_queue(self) -> None: ...
    async def is_alive(self) -> bool: ...
    async def get_current(self) -> Optional[str]: ...


def select_engine() -> StreamEngine:
    if shutil.which("liquidsoap"):
        return LiquidsoapEngine()
    if shutil.which("ffmpeg"):
        return FfmpegEngine()
    raise RuntimeError("dj_booth: neither liquidsoap nor ffmpeg is installed")


class FfmpegEngine:
    """
    Fallback engine. Maintains an asyncio queue of track paths and spawns
    one ffmpeg per track that streams directly to the icecast source.
    No crossfade. Brief silence between tracks is expected.
    """
    name = "ffmpeg"

    def __init__(self):
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.config: dict = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._current_proc: Optional[asyncio.subprocess.Process] = None
        self._current_path: str = ""
        self._failure_streak: int = 0

    async def start(self, config: dict, initial_tracks: list[str]) -> None:
        self.config = config
        for t in initial_tracks:
            await self.queue.put(t)
        self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        await self._kill_current()
        while not self.queue.empty():
            self.queue.get_nowait()

    async def queue_track(self, path: str) -> None:
        await self.queue.put(path)

    async def skip(self) -> None:
        await self._kill_current()

    async def clear_queue(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()

    async def is_alive(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    async def get_current(self) -> Optional[str]:
        return self._current_path or None

    async def _kill_current(self) -> None:
        if self._current_proc and self._current_proc.returncode is None:
            try:
                self._current_proc.terminate()
                try:
                    await asyncio.wait_for(self._current_proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self._current_proc.kill()
                    await self._current_proc.wait()
            except ProcessLookupError:
                pass
        self._current_proc = None
        self._current_path = ""

    async def _loop(self) -> None:
        cfg = self.config
        port = int(cfg.get("icecast_port", 8000))
        bitrate = int(cfg.get("bitrate", 192))
        sample_rate = int(cfg.get("sample_rate", 44100))
        mount = cfg.get("mount", "/stream")
        password = cfg["icecast_source_password"]
        icecast_url = f"icecast://source:{password}@localhost:{port}{mount}"

        while True:
            try:
                path: str
                try:
                    path = self.queue.get_nowait()
                    self._current_path = path
                    cmd = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-re", "-i", path,
                        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
                        "-ar", str(sample_rate), "-ac", "2",
                        "-content_type", "audio/mpeg", "-f", "mp3",
                        icecast_url,
                    ]
                except asyncio.QueueEmpty:
                    self._current_path = ""
                    cmd = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-re", "-f", "lavfi",
                        "-i", f"anullsrc=r={sample_rate}:cl=stereo",
                        "-t", "5",
                        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
                        "-content_type", "audio/mpeg", "-f", "mp3",
                        icecast_url,
                    ]
                self._current_proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                rc = await self._current_proc.wait()
                if rc != 0 and self._current_path:
                    self._failure_streak += 1
                    log.warning("dj_booth ffmpeg failed for %s rc=%d", self._current_path, rc)
                    if self._failure_streak >= 3:
                        log.error("dj_booth ffmpeg engine: 3 consecutive failures, exiting loop")
                        return
                else:
                    self._failure_streak = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("dj_booth ffmpeg loop error")
                await asyncio.sleep(0.5)


class LiquidsoapEngine:
    name = "liquidsoap"

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.config: dict = {}

    async def start(self, config: dict, initial_tracks: list[str]) -> None:
        self.config = config
        from pathlib import Path as _P
        _P(LIQ_SCRIPT_PATH).write_text(render_liq_script(config))
        self.process = await asyncio.create_subprocess_exec(
            "liquidsoap", LIQ_SCRIPT_PATH,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # liquidsoap takes ~1-2s to bind telnet port — retry
        last_err: Optional[Exception] = None
        for _ in range(15):
            await asyncio.sleep(0.2)
            if self.process.returncode is not None:
                raise RuntimeError(f"liquidsoap exited rc={self.process.returncode}")
            try:
                await self._telnet_send("version")
                last_err = None
                break
            except (ConnectionRefusedError, OSError) as e:
                last_err = e
        if last_err is not None:
            await self.stop()
            raise RuntimeError(f"liquidsoap telnet failed: {last_err}")
        for path in initial_tracks:
            await self.queue_track(path)

    async def stop(self) -> None:
        if self.process is None:
            return
        try:
            try:
                await asyncio.wait_for(self._telnet_send("quit"), timeout=1.0)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
        except ProcessLookupError:
            pass
        self.process = None
        try:
            import os as _os
            _os.unlink(LIQ_SCRIPT_PATH)
        except FileNotFoundError:
            pass

    async def queue_track(self, path: str) -> None:
        await self._telnet_send(f"main.push {path}")

    async def skip(self) -> None:
        await self._telnet_send("main.skip")

    async def clear_queue(self) -> None:
        # Liquidsoap has no built-in queue purge; skip until empty.
        # Slice 1: cap at 100 skips defensively.
        for _ in range(100):
            resp = await self._telnet_send("main.length")
            try:
                if int(resp.strip()) == 0:
                    return
            except ValueError:
                return
            await self._telnet_send("main.skip")

    async def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def get_current(self) -> Optional[str]:
        try:
            rid = (await self._telnet_send("request.on_air")).strip()
            if not rid or rid == "":
                return None
            meta = await self._telnet_send(f"request.metadata {rid}")
            artist = title = ""
            for line in meta.splitlines():
                if line.startswith('artist="'):
                    artist = line.split('"', 2)[1]
                elif line.startswith('title="'):
                    title = line.split('"', 2)[1]
            if artist or title:
                return f"{artist} - {title}".strip(" -")
            return None
        except Exception:
            return None

    async def _telnet_send(self, command: str) -> str:
        reader, writer = await asyncio.open_connection(LIQ_TELNET_HOST, LIQ_TELNET_PORT)
        try:
            writer.write((command + "\n").encode())
            await writer.drain()
            buf = b""
            while True:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=2.0)
                if not chunk:
                    break
                buf += chunk
                if b"END\r\n" in buf or b"END\n" in buf:
                    break
            text = buf.decode(errors="replace")
            for marker in ("END\r\n", "END\n"):
                if text.endswith(marker):
                    text = text[: -len(marker)]
                    break
            return text
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
