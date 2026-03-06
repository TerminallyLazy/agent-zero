from __future__ import annotations

import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Optional

from helpers import files
from helpers.plugins import (
    META_FILE_NAME,
    PluginMetadata,
    invalidate_plugin_cache,
)
from helpers import yaml as yaml_helper

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_]*$")


def _get_user_plugins_dir() -> str:
    """Return absolute path to usr/plugins/."""
    return files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR)


def _sanitize_plugin_name(name: str) -> str:
    """Validate and sanitize a plugin directory name.
    Converts dots and dashes to underscores for Python import compatibility.
    Raises ValueError if the name is unsafe for filesystem use."""
    name = name.strip().strip(".")
    name = re.sub(r"[-.]", "_", name)
    if not name or not _SAFE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid plugin name: '{name}'. "
            "Names must start with a letter or digit and contain only letters, digits, or underscores."
        )
    return name


def validate_plugin_dir(path: str) -> PluginMetadata:
    """Check directory contains plugin.yaml and return parsed metadata.
    Raises ValueError if plugin.yaml is missing or invalid."""
    meta_path = os.path.join(path, META_FILE_NAME)
    if not os.path.isfile(meta_path):
        raise ValueError(f"No {META_FILE_NAME} found in {os.path.basename(path)}")
    with open(meta_path, "r", encoding="utf-8") as f:
        content = f.read()
    data = yaml_helper.loads(content)
    return PluginMetadata.model_validate(data)


def check_plugin_conflict(name: str) -> None:
    """Raise ValueError if a plugin with this name already exists in usr/plugins/."""
    dest = os.path.join(_get_user_plugins_dir(), name)
    if os.path.exists(dest):
        raise ValueError(f"Plugin '{name}' is already installed")


def _find_plugin_root(extracted_dir: str) -> str:
    """Walk extracted directory to find the parent of plugin.yaml.
    Returns absolute path to the plugin root directory."""
    for root, dirs, dir_files in os.walk(extracted_dir):
        if META_FILE_NAME in dir_files:
            return root
    raise ValueError(f"No {META_FILE_NAME} found in the uploaded archive")


def install_from_zip(zip_path: str) -> dict:
    """Extract ZIP, find plugin.yaml, move its parent to usr/plugins/.
    Returns dict with plugin name and metadata.
    Cleans up tmp files regardless of outcome."""
    base_tmp = files.get_abs_path("tmp", "plugin_installs")
    os.makedirs(base_tmp, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    extract_dir = os.path.join(base_tmp, f"extract_{stamp}")
    os.makedirs(extract_dir, exist_ok=True)

    try:
        # Extract with path traversal protection
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                real_extract = os.path.realpath(extract_dir)
                for member in z.namelist():
                    member_path = os.path.realpath(os.path.join(extract_dir, member))
                    if not member_path.startswith(real_extract + os.sep) and member_path != real_extract:
                        raise ValueError(f"Unsafe path in archive: {member}")
                z.extractall(extract_dir)
        except zipfile.BadZipFile:
            raise ValueError("The uploaded file is not a valid ZIP archive")

        # Find plugin.yaml
        plugin_root = _find_plugin_root(extract_dir)
        meta = validate_plugin_dir(plugin_root)
        plugin_name = os.path.basename(plugin_root)

        # If the zip only has one top-level dir that IS the plugin root,
        # use that dir's name. Otherwise use the zip's stem.
        if plugin_root == extract_dir:
            # plugin.yaml at root of extraction — use zip filename stem
            plugin_name = Path(zip_path).stem

        plugin_name = _sanitize_plugin_name(plugin_name)
        check_plugin_conflict(plugin_name)

        # Move to usr/plugins/
        dest = os.path.join(_get_user_plugins_dir(), plugin_name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(plugin_root, dest)
        invalidate_plugin_cache()

        return {
            "success": True,
            "plugin_name": plugin_name,
            "title": meta.title or plugin_name,
            "path": files.deabsolute_path(dest),
        }
    finally:
        # Cleanup: extracted files and the archive
        shutil.rmtree(extract_dir, ignore_errors=True)
        try:
            os.unlink(zip_path)
        except OSError:
            pass


def install_from_git(url: str, token: Optional[str] = None) -> dict:
    """Clone git repo into usr/plugins/, validate plugin.yaml.
    Returns dict with plugin name and metadata."""
    from helpers.git import clone_repo

    # Derive plugin name from URL
    repo_name = url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    if not repo_name:
        raise ValueError("Could not derive plugin name from URL")

    repo_name = _sanitize_plugin_name(repo_name)
    check_plugin_conflict(repo_name)

    dest = os.path.join(_get_user_plugins_dir(), repo_name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    try:
        clone_repo(url, dest, token=token or None)
    except Exception as e:
        # Cleanup partial clone
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError(f"Git clone failed: {e}") from e

    try:
        meta = validate_plugin_dir(dest)
    except ValueError:
        # No plugin.yaml — remove cloned repo
        shutil.rmtree(dest, ignore_errors=True)
        raise

    invalidate_plugin_cache()

    return {
        "success": True,
        "plugin_name": repo_name,
        "title": meta.title or repo_name,
        "path": files.deabsolute_path(dest),
    }


def fetch_plugin_index() -> dict:
    """Download the plugin index from GitHub releases."""
    import urllib.request
    import json

    index_url = "https://github.com/agent0ai/a0-plugins/releases/download/generated-index/index.json"
    req = urllib.request.Request(index_url, headers={"User-Agent": "AgentZero"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data
