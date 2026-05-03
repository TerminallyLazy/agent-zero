"""Icecast2 process manager: writes config, spawns icecast2, polls listener count."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from pathlib import Path
from typing import Optional

import urllib.request
import urllib.error


log = logging.getLogger(__name__)


ICECAST_XML_TEMPLATE = """<icecast>
  <location>localhost</location>
  <admin>admin@localhost</admin>
  <limits>
    <clients>{max_listeners}</clients>
    <sources>2</sources>
    <queue-size>524288</queue-size>
    <client-timeout>30</client-timeout>
    <header-timeout>15</header-timeout>
    <source-timeout>10</source-timeout>
  </limits>
  <authentication>
    <source-password>{source_password}</source-password>
    <relay-password>{relay_password}</relay-password>
    <admin-user>admin</admin-user>
    <admin-password>{admin_password}</admin-password>
  </authentication>
  <hostname>localhost</hostname>
  <listen-socket>
    <port>{port}</port>
  </listen-socket>
  <mount>
    <mount-name>{mount}</mount-name>
    <max-listeners>{max_listeners}</max-listeners>
    <stream-name>{stream_name}</stream-name>
    <stream-description>{stream_description}</stream-description>
    <stream-url>{stream_url}</stream-url>
    <genre>{stream_genre}</genre>
    <public>{public_int}</public>
  </mount>
  <fileserve>1</fileserve>
  <paths>
    <basedir>/usr/share/icecast2</basedir>
    <logdir>/tmp/dj_booth_logs</logdir>
    <webroot>/usr/share/icecast2/web</webroot>
    <adminroot>/usr/share/icecast2/admin</adminroot>
    <pidfile>/tmp/dj_booth_icecast.pid</pidfile>
  </paths>
  <logging>
    <accesslog>access.log</accesslog>
    <errorlog>error.log</errorlog>
    <loglevel>3</loglevel>
  </logging>
  <security>
    <chroot>0</chroot>
  </security>
</icecast>
"""

XML_CONFIG_PATH = "/tmp/dj_booth_icecast.xml"
PIDFILE = "/tmp/dj_booth_icecast.pid"
LOG_DIR = "/tmp/dj_booth_logs"


def render_icecast_xml(cfg: dict) -> str:
    return ICECAST_XML_TEMPLATE.format(
        max_listeners=int(cfg.get("max_listeners", 100)),
        source_password=cfg["icecast_source_password"],
        relay_password=cfg.get("icecast_relay_password", cfg["icecast_admin_password"]),
        admin_password=cfg["icecast_admin_password"],
        port=int(cfg["icecast_port"]),
        mount=cfg.get("mount", "/stream"),
        stream_name=cfg.get("stream_name", "Stream"),
        stream_description=cfg.get("stream_description", ""),
        stream_url=cfg.get("stream_url", ""),
        stream_genre=cfg.get("stream_genre", ""),
        public_int=1 if cfg.get("public_listing") else 0,
    )


class IcecastManager:
    _instance: Optional["IcecastManager"] = None

    @classmethod
    def get(cls) -> "IcecastManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.config: dict = {}
        self.mode: str = ""  # "icecast2" | "python" | ""
        self.python_server = None  # IcyServer instance when mode == "python"

    async def start(self, config: dict) -> None:
        self.config = config
        os.makedirs(LOG_DIR, exist_ok=True)

        # Pick implementation: external icecast2 if available, else built-in Python server.
        # The Python server speaks the same ICY-over-HTTP protocol so listener clients
        # (VLC, Winamp, browsers) can't tell the difference.
        import shutil as _shutil
        if _shutil.which("icecast2"):
            await self._start_icecast2()
            self.mode = "icecast2"
        else:
            await self._start_python_server()
            self.mode = "python"
        log.info("dj_booth: streaming server started (mode=%s)", self.mode)

    async def _start_icecast2(self) -> None:
        Path(XML_CONFIG_PATH).write_text(render_icecast_xml(self.config))
        log.info("dj_booth: starting icecast2 with %s", XML_CONFIG_PATH)
        self.process = await asyncio.create_subprocess_exec(
            "icecast2", "-c", XML_CONFIG_PATH,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.sleep(0.5)
        if self.process.returncode is not None:
            raise RuntimeError(f"icecast2 exited immediately, code {self.process.returncode}")

    async def _start_python_server(self) -> None:
        from usr.plugins.dj_booth.helpers.icy_server import IcyServer
        self.python_server = IcyServer(
            port=int(self.config["icecast_port"]),
            mount=self.config.get("mount", "/stream"),
            stream_name=self.config.get("stream_name", "Stream"),
            stream_description=self.config.get("stream_description", ""),
            stream_genre=self.config.get("stream_genre", ""),
        )
        await self.python_server.start()

    async def stop(self) -> None:
        if self.python_server is not None:
            try:
                await self.python_server.stop()
            except Exception:
                log.exception("dj_booth: python server stop error")
            self.python_server = None
        if self.process is not None:
            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            except ProcessLookupError:
                pass
            self.process = None
            for path in (XML_CONFIG_PATH, PIDFILE):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
        self.mode = ""

    async def is_alive(self) -> bool:
        if self.mode == "python":
            return self.python_server is not None and self.python_server.is_running
        return self.process is not None and self.process.returncode is None

    async def push_audio(self, data: bytes) -> None:
        """Feed audio bytes into the in-process Python server. No-op for icecast2 mode
        (in icecast2 mode, the engine writes directly to icecast2's HTTP source endpoint)."""
        if self.python_server is not None:
            await self.python_server.push_chunk(data)

    def set_now_playing(self, display: str) -> None:
        if self.python_server is not None:
            self.python_server.set_current_track(display)

    async def get_listener_count(self) -> int:
        if self.python_server is not None:
            return self.python_server.listener_count
        port = int(self.config.get("icecast_port", 8000))
        mount = self.config.get("mount", "/stream")
        url = f"http://localhost:{port}/status-json.xsl"
        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(url, timeout=2).read().decode("utf-8")
            )
        except (urllib.error.URLError, OSError):
            return 0
        return self.parse_listener_count(text, mount)

    @staticmethod
    def parse_listener_count(text: str, mount: str) -> int:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return 0
        source = data.get("icestats", {}).get("source")
        if source is None:
            return 0
        if isinstance(source, list):
            for entry in source:
                if isinstance(entry, dict) and entry.get("listenurl", "").endswith(mount):
                    return int(entry.get("listeners", 0))
            return 0
        if isinstance(source, dict):
            return int(source.get("listeners", 0))
        return 0
