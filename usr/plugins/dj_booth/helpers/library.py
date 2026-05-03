"""Music library scanner using mutagen for tag extraction."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".wav", ".aiff", ".aif"}


@dataclass
class Track:
    path: str
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    year: str = ""
    duration: float = 0.0
    file_size: int = 0
    format: str = ""
    bpm: float = 0.0
    key: str = ""
    waveform_peaks: list[float] = field(default_factory=list)


def compute_waveform(path: str, bucket_count: int = 1000) -> list[float]:
    try:
        import subprocess
        import numpy as np
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", path, "-f", "f32le", "-ac", "1", "-ar", "8000", "-"],
            capture_output=True, timeout=60,
        )
        if proc.returncode != 0 or not proc.stdout:
            return []
        pcm = np.frombuffer(proc.stdout, dtype=np.float32)
        if pcm.size == 0:
            return []
        bucket_size = max(1, pcm.size // bucket_count)
        buckets = []
        for i in range(bucket_count):
            chunk = pcm[i * bucket_size:(i + 1) * bucket_size]
            if chunk.size:
                buckets.append(float(np.abs(chunk).max()))
            else:
                buckets.append(0.0)
        peak = max(buckets) or 1.0
        return [b / peak for b in buckets]
    except Exception:
        return []


class LibraryManager:
    """Scans a directory and exposes tracks. Not a singleton — kept on the plugin runtime."""

    def __init__(self):
        self.tracks: list[Track] = []
        self.index: dict[str, Track] = {}
        self.last_dir: str = ""

    def scan(self, music_dir: str) -> int:
        self.tracks.clear()
        self.index.clear()
        self.last_dir = music_dir
        if not os.path.isdir(music_dir):
            return 0
        for root, _dirs, files in os.walk(music_dir):
            for name in files:
                p = Path(root) / name
                if p.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue
                track = self._read_track(str(p))
                if track is not None:
                    self.tracks.append(track)
                    self.index[track.path] = track
        return len(self.tracks)

    def _read_track(self, path: str) -> Optional[Track]:
        try:
            stem = Path(path).stem
            ext = Path(path).suffix.lower().lstrip(".")
            size = os.path.getsize(path)
            track = Track(
                path=path,
                title=stem,
                artist="Unknown Artist",
                file_size=size,
                format=ext,
            )
            try:
                import mutagen
                meta = mutagen.File(path, easy=True)
                if meta is not None:
                    if meta.tags:
                        track.title = (meta.tags.get("title", [stem])[0] or stem)
                        track.artist = (meta.tags.get("artist", ["Unknown Artist"])[0] or "Unknown Artist")
                        track.album = (meta.tags.get("album", [""])[0] or "")
                        track.genre = (meta.tags.get("genre", [""])[0] or "")
                        track.year = (meta.tags.get("date", [""])[0] or "")
                    if meta.info is not None:
                        track.duration = float(getattr(meta.info, "length", 0.0))
            except Exception:
                pass
            return track
        except OSError:
            return None

    def search(self, query: str) -> list[Track]:
        q = query.lower()
        return [
            t for t in self.tracks
            if q in t.title.lower()
            or q in t.artist.lower()
            or q in t.album.lower()
            or q in t.genre.lower()
        ]

    def get_track(self, path: str) -> Optional[Track]:
        return self.index.get(path)

    async def analyze(self, path: str) -> Optional[Track]:
        t = self.get_track(path)
        if t is None:
            return None
        from usr.plugins.dj_booth.helpers import bpm_key
        import asyncio
        loop = asyncio.get_event_loop()
        t.bpm = await bpm_key.detect_bpm(path)
        t.key = await bpm_key.detect_key(path)
        t.waveform_peaks = await loop.run_in_executor(None, compute_waveform, path)
        return t
