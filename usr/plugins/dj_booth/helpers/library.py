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
