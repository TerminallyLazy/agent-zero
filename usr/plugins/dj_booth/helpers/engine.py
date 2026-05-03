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
    """Placeholder — full impl in Task 6."""
    name = "liquidsoap"
    async def start(self, config: dict, initial_tracks: list[str]) -> None:
        raise NotImplementedError("Task 6")
    async def stop(self) -> None: pass
    async def queue_track(self, path: str) -> None: pass
    async def skip(self) -> None: pass
    async def clear_queue(self) -> None: pass
    async def is_alive(self) -> bool: return False
    async def get_current(self) -> Optional[str]: return None
