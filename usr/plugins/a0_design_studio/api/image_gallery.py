"""API handler for image gallery management."""
from __future__ import annotations

import base64
import json
import os
import time
import sys
from pathlib import Path

from python.helpers.api import ApiHandler, Input, Request

_plugin_root = Path(__file__).parent.parent
if str(_plugin_root) not in sys.path:
    sys.path.insert(0, str(_plugin_root))

from helpers.image_providers import get_plugin_config


class ImageGallery(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: Input, request: Request) -> dict:
        action = input.get("action", "list")
        config = get_plugin_config()
        gallery_path = input.get("gallery_path") or config.get("gallery_path", "images")

        if action == "list":
            return self._list_images(gallery_path)
        elif action == "save":
            return self._save_image(input, gallery_path)
        elif action == "delete":
            return self._delete_image(input, gallery_path)
        elif action == "get":
            return self._get_image(input, gallery_path)
        else:
            return {"error": f"Unknown action: {action}", "images": []}

    def _list_images(self, gallery_path: str) -> dict:
        if not os.path.isdir(gallery_path):
            return {"images": []}
        images = []
        for fname in sorted(os.listdir(gallery_path), reverse=True):
            if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            fpath = os.path.join(gallery_path, fname)
            meta_path = fpath + ".json"
            metadata = {}
            if os.path.isfile(meta_path):
                with open(meta_path, "r") as f:
                    metadata = json.load(f)
            images.append({
                "filename": fname,
                "path": fpath,
                "timestamp": os.path.getmtime(fpath),
                "prompt": metadata.get("prompt", ""),
                "model": metadata.get("model", ""),
            })
        return {"images": images}

    def _save_image(self, input: Input, gallery_path: str) -> dict:
        image_b64 = input.get("image_b64", "")
        filename = input.get("filename", f"image_{int(time.time())}.png")
        metadata = input.get("metadata", {})
        if not image_b64:
            return {"error": "image_b64 is required", "success": False}
        os.makedirs(gallery_path, exist_ok=True)
        fpath = os.path.join(gallery_path, filename)
        with open(fpath, "wb") as f:
            f.write(base64.b64decode(image_b64))
        if metadata:
            meta_path = fpath + ".json"
            with open(meta_path, "w") as f:
                json.dump(metadata, f)
        return {"success": True, "path": fpath, "filename": filename}

    def _delete_image(self, input: Input, gallery_path: str) -> dict:
        filename = input.get("filename", "")
        if not filename:
            return {"error": "filename is required", "success": False}
        fpath = os.path.join(gallery_path, filename)
        meta_path = fpath + ".json"
        if os.path.isfile(fpath):
            os.remove(fpath)
        if os.path.isfile(meta_path):
            os.remove(meta_path)
        return {"success": True}

    def _get_image(self, input: Input, gallery_path: str) -> dict:
        filename = input.get("filename", "")
        if not filename:
            return {"error": "filename is required"}
        fpath = os.path.join(gallery_path, filename)
        if not os.path.isfile(fpath):
            return {"error": f"Image not found: {filename}"}
        with open(fpath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        meta_path = fpath + ".json"
        metadata = {}
        if os.path.isfile(meta_path):
            with open(meta_path, "r") as mf:
                metadata = json.load(mf)
        return {"image_b64": b64, "filename": filename, "metadata": metadata}
