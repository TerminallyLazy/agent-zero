"""Microphone capture stub — Slice 5 ships interface; full impl deferred."""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


class MicCapture:
    """Stub. start()/stop() return without doing anything; list_devices returns []."""
    _instance: Optional["MicCapture"] = None

    @classmethod
    def get(cls) -> "MicCapture":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.active = False
        self.volume = 0.8
        self.device_index = 0

    async def start(self, device_index: int = 0) -> bool:
        log.warning("dj_booth: mic capture not yet implemented (stub)")
        self.device_index = device_index
        self.active = False  # always remains False until real impl
        return False

    async def stop(self) -> None:
        self.active = False

    def set_volume(self, level: float) -> None:
        self.volume = max(0.0, min(2.0, float(level)))

    @staticmethod
    def list_devices() -> list[dict]:
        # Real impl: pyaudio.PyAudio().get_device_info_by_index(...)
        return []
