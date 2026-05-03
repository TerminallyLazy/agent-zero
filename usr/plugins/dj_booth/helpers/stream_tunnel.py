"""Optional Cloudflare quick tunnel for the stream port.

Lets non-technical users share their stream with anyone on the internet
without router/firewall configuration. Uses flaredantic (already an A0
dependency) which downloads/wraps the cloudflared binary and creates a
free public URL like https://something-random.trycloudflare.com.

Singleton — only one stream tunnel at a time.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional


log = logging.getLogger(__name__)


class StreamTunnel:
    _instance: Optional["StreamTunnel"] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get(cls) -> "StreamTunnel":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._tunnel = None
        self._tunnel_url: str = ""
        self._port: int = 0
        self._error: str = ""
        self._starting: bool = False

    @property
    def url(self) -> str:
        return self._tunnel_url

    @property
    def is_running(self) -> bool:
        return self._tunnel is not None and bool(self._tunnel_url)

    @property
    def is_starting(self) -> bool:
        return self._starting

    @property
    def last_error(self) -> str:
        return self._error

    def start(self, port: int, timeout: float = 30.0) -> str:
        """
        Start a Cloudflare quick tunnel pointing to localhost:port.
        Returns the public URL or "" on failure (with last_error set).
        Idempotent: if already running for the same port, returns existing URL.
        """
        if self.is_running and self._port == port:
            return self._tunnel_url
        if self.is_running:
            # Different port — restart
            self.stop()

        self._error = ""
        self._port = port
        self._starting = True

        try:
            from flaredantic import FlareTunnel, FlareConfig
        except ImportError as e:
            self._error = f"flaredantic not installed: {e}"
            self._starting = False
            return ""

        try:
            config = FlareConfig(port=port, verbose=False)
            self._tunnel = FlareTunnel(config)

            def _run():
                try:
                    self._tunnel.start()
                except Exception as e:
                    self._error = f"tunnel failed: {e}"
                    log.exception("dj_booth: tunnel failed")

            t = threading.Thread(target=_run, daemon=True)
            t.start()

            # Poll for URL up to timeout
            deadline = time.time() + timeout
            while time.time() < deadline:
                url = getattr(self._tunnel, "tunnel_url", None)
                if url:
                    self._tunnel_url = url
                    self._starting = False
                    return url
                if self._error:
                    break
                time.sleep(0.2)

            if not self._tunnel_url:
                self._error = self._error or "timed out waiting for tunnel URL"
                # Best-effort cleanup
                try:
                    self._tunnel.stop()
                except Exception:
                    pass
                self._tunnel = None
        except Exception as e:
            self._error = f"could not start tunnel: {e}"
            self._tunnel = None
            log.exception("dj_booth: tunnel start error")

        self._starting = False
        return self._tunnel_url

    def stop(self) -> None:
        if self._tunnel is not None:
            try:
                self._tunnel.stop()
            except Exception:
                log.exception("dj_booth: tunnel stop error")
            self._tunnel = None
        self._tunnel_url = ""
        self._port = 0
        self._error = ""
        self._starting = False
