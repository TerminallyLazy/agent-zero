from __future__ import annotations

import time
import uuid
from pathlib import Path

from helpers.api import ApiHandler, Input, Request, Output
from helpers import files
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


class PluginInstall(ApiHandler):
    """Plugin installation API. Handles ZIP upload, Git clone, and index fetch."""

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "") or request.form.get("action", "")

        try:
            if action == "install_zip":
                return self._install_zip(request)
            elif action == "install_git":
                return self._install_git(input)
            elif action == "fetch_index":
                return self._fetch_index(input)
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Installation failed: {e}"}

    def _install_zip(self, request: Request) -> dict:
        if "plugin_file" not in request.files:
            return {"success": False, "error": "No file provided"}

        plugin_file: FileStorage = request.files["plugin_file"]
        if not plugin_file.filename:
            return {"success": False, "error": "No file selected"}

        # Save upload to temp
        tmp_dir = Path(files.get_abs_path("tmp", "plugin_uploads"))
        tmp_dir.mkdir(parents=True, exist_ok=True)
        base = secure_filename(plugin_file.filename)
        if not base.lower().endswith(".zip"):
            base = f"{base}.zip"
        unique = uuid.uuid4().hex[:8]
        stamp = time.strftime("%Y%m%d_%H%M%S")
        tmp_path = str(tmp_dir / f"plugin_{stamp}_{unique}_{base}")
        plugin_file.save(tmp_path)

        from plugins.plugin_installer.helpers.install import install_from_zip
        return install_from_zip(tmp_path)

    def _install_git(self, input: dict) -> dict:
        git_url = (input.get("git_url", "") or "").strip()
        git_token = (input.get("git_token", "") or "").strip() or None
        if not git_url:
            return {"success": False, "error": "Git URL is required"}

        from plugins.plugin_installer.helpers.install import install_from_git
        return install_from_git(git_url, git_token)

    def _fetch_index(self, input: dict) -> dict:
        from plugins.plugin_installer.helpers.install import fetch_plugin_index
        from helpers.plugins import get_plugins_list
        index_data = fetch_plugin_index()
        installed = get_plugins_list()
        return {
            "success": True,
            "index": index_data,
            "installed_plugins": installed,
        }
