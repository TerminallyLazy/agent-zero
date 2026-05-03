"""Drag-and-drop / file-picker upload endpoint for the music library.

Accepts multipart form-data with files[] field, saves each file into the
configured music_dir, then triggers a library re-scan and returns the
fresh track count.

Designed for non-technical users who can't / shouldn't have to map a
Docker volume to get music into the plugin. Drop files in the UI, they
land in /a0/usr/workdir/music inside the container.
"""
from __future__ import annotations

import os
from werkzeug.utils import secure_filename
from helpers.api import ApiHandler, Request
from helpers.plugins import get_plugin_config

from usr.plugins.dj_booth.api.dj_control import _get_library
from usr.plugins.dj_booth.helpers.library import discover_music_dirs
from usr.plugins.dj_booth.helpers.state import get_state


AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".wav", ".aiff", ".aif"}


class UploadTrack(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        if "files[]" not in request.files:
            return {"error": "No files in upload."}

        cfg = get_plugin_config("dj_booth") or {}
        music_dir = cfg.get("music_dir", "/a0/usr/workdir/music")
        os.makedirs(music_dir, exist_ok=True)

        uploaded = request.files.getlist("files[]")
        successful: list[str] = []
        failed: list[dict] = []
        rejected: list[str] = []

        for file_storage in uploaded:
            raw_name = file_storage.filename or ""
            ext = os.path.splitext(raw_name)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                rejected.append(raw_name)
                continue
            safe = secure_filename(raw_name) or f"track{ext}"
            dst = os.path.join(music_dir, safe)
            # Avoid overwriting existing files: append (1), (2)...
            base, e = os.path.splitext(dst)
            n = 1
            while os.path.exists(dst):
                dst = f"{base} ({n}){e}"
                n += 1
            try:
                file_storage.save(dst)
                successful.append(os.path.basename(dst))
            except Exception as ex:
                failed.append({"name": raw_name, "error": str(ex)})

        # Auto-scan so the new files show up immediately in the library list.
        # Sync scan in this thread is fine — uploads block until done anyway.
        if successful:
            lib = _get_library()
            paths = discover_music_dirs(music_dir)
            count = lib.scan(paths)
            s = get_state()
            s.library_count = count
            s.last_scan_at = lib.last_scan_at
            s.scanned_paths = list(lib.scanned_paths)
            s.scanned_path_counts = dict(lib.scanned_path_counts)

        return {
            "uploaded": successful,
            "rejected_non_audio": rejected,
            "failed": failed,
            "music_dir": music_dir,
            "library_count": get_state().library_count,
        }
