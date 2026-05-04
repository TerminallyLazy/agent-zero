"""Drag-and-drop / file-picker upload endpoint for the music library.

Accepts multipart form-data with files[] field, saves each file into the
configured music_dir, then triggers a library re-scan and returns the
fresh track count.

Designed for non-technical users who can't / shouldn't have to map a
Docker volume to get music into the plugin. Drop files in the UI, they
land in /a0/usr/workdir/music inside the container.
"""
from __future__ import annotations

import logging
import os
import traceback

from helpers.api import ApiHandler, Request


log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".wav", ".aiff", ".aif"}


class UploadTrack(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        # Catch absolutely everything and return a JSON error rather than
        # letting Flask render an HTML 500 page. The frontend always parses
        # res.json(); HTML breaks it.
        try:
            return await self._do_upload(request)
        except Exception as e:
            log.exception("dj_booth: upload error")
            return {
                "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc().splitlines()[-5:],
                "uploaded": [],
                "rejected_non_audio": [],
                "failed": [],
            }

    async def _do_upload(self, request: Request) -> dict:
        # Imports done here (not at module top) so a transient import error
        # in a sibling module doesn't prevent A0 from loading this handler at all.
        from werkzeug.utils import secure_filename
        from helpers.plugins import get_plugin_config
        from usr.plugins.dj_booth.helpers import library as library_mod
        from usr.plugins.dj_booth.helpers.state import get_state

        if "files[]" not in request.files:
            # Friendlier hint than just "no files".
            return {
                "error": "No files received. Try drag-and-dropping again, or use the + Add Music button.",
                "uploaded": [], "rejected_non_audio": [], "failed": [],
            }

        cfg = get_plugin_config("dj_booth") or {}
        music_dir = cfg.get("music_dir", "/a0/usr/workdir/music")
        try:
            os.makedirs(music_dir, exist_ok=True)
        except Exception as e:
            return {
                "error": f"Couldn't create music folder '{music_dir}': {e}",
                "uploaded": [], "rejected_non_audio": [], "failed": [],
            }

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

        # Auto-rescan so the new files show up immediately. Use a fresh
        # LibraryManager singleton lookup rather than importing _get_library
        # from dj_control (avoids any circular-import risk during dispatch).
        if successful:
            from usr.plugins.dj_booth.api import dj_control
            lib = dj_control._get_library()
            # Prefer multi-path discovery if the running plugin has the newer
            # library module; fall back to single-dir scan when it doesn't.
            # Also handle older LibraryManager.scan that only accepts a str.
            discover = getattr(library_mod, "discover_music_dirs", None)
            try:
                if callable(discover):
                    count = lib.scan(discover(music_dir))
                else:
                    count = lib.scan(music_dir)
            except TypeError:
                # Older scan signature didn't accept a list — single dir.
                count = lib.scan(music_dir)
            s = get_state()
            s.library_count = count
            for attr_name, value in (
                ("last_scan_at", getattr(lib, "last_scan_at", 0.0)),
                ("scanned_paths", list(getattr(lib, "scanned_paths", []) or [])),
                ("scanned_path_counts", dict(getattr(lib, "scanned_path_counts", {}) or {})),
            ):
                if hasattr(s, attr_name):
                    setattr(s, attr_name, value)

        return {
            "uploaded": successful,
            "rejected_non_audio": rejected,
            "failed": failed,
            "music_dir": music_dir,
            "library_count": get_state().library_count,
        }
