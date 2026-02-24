"""Git operations for marketplace plugin installation."""

import os
import shutil
import subprocess
from pathlib import Path
from python.helpers import files

USR_PLUGINS_DIR = files.get_abs_path("usr", "plugins")


def clone_plugin(repo_url: str, plugin_path: str, plugin_id: str, branch: str = "") -> dict:
    """
    Clone a plugin from a git repo into usr/plugins/<plugin_id>.

    If plugin_path is "." or empty, the repo root IS the plugin.
    If plugin_path is e.g. "plugins/memory", uses sparse checkout.
    If branch is provided, clones from that specific branch.

    Returns {"ok": True} or {"ok": False, "error": "..."}.
    """
    target_dir = os.path.join(USR_PLUGINS_DIR, plugin_id)

    if os.path.exists(target_dir):
        return {"ok": False, "error": f"Plugin '{plugin_id}' is already installed."}

    os.makedirs(USR_PLUGINS_DIR, exist_ok=True)

    # Sanitize repo_url: strip GitHub tree/blob UI paths
    # e.g. "https://github.com/user/repo/tree/branch" -> "https://github.com/user/repo"
    repo_url = _clean_github_url(repo_url)

    is_subdirectory = plugin_path and plugin_path != "."

    try:
        if is_subdirectory:
            return _sparse_clone(repo_url, plugin_path, plugin_id, target_dir, branch=branch)
        else:
            return _full_clone(repo_url, target_dir, branch=branch)
    except Exception as e:
        # Clean up on failure
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)
        return {"ok": False, "error": str(e)}


def _clean_github_url(url: str) -> str:
    """Strip /tree/... or /blob/... suffixes from GitHub web UI URLs."""
    for marker in ("/tree/", "/blob/"):
        idx = url.find(marker)
        if idx != -1:
            return url[:idx]
    return url


def _full_clone(repo_url: str, target_dir: str, branch: str = "") -> dict:
    """Clone the entire repo as the plugin directory."""
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [repo_url, target_dir]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        return {"ok": False, "error": f"git clone failed: {result.stderr.strip()}"}

    # Remove .git dir to save space
    git_dir = os.path.join(target_dir, ".git")
    if os.path.exists(git_dir):
        shutil.rmtree(git_dir, ignore_errors=True)

    # Validate plugin.json exists
    if not os.path.exists(os.path.join(target_dir, "plugin.json")):
        shutil.rmtree(target_dir, ignore_errors=True)
        return {"ok": False, "error": "Cloned repo has no plugin.json at root."}

    return {"ok": True}


def _sparse_clone(repo_url: str, plugin_path: str, plugin_id: str, target_dir: str, branch: str = "") -> dict:
    """Clone only a subdirectory of a repo."""
    tmp_dir = target_dir + "_tmp_clone"
    try:
        # Init empty repo
        subprocess.run(["git", "init", tmp_dir], capture_output=True, text=True, check=True)
        subprocess.run(
            ["git", "-C", tmp_dir, "remote", "add", "origin", repo_url],
            capture_output=True, text=True, check=True
        )
        subprocess.run(
            ["git", "-C", tmp_dir, "config", "core.sparseCheckout", "true"],
            capture_output=True, text=True, check=True
        )

        # Write sparse-checkout pattern
        sparse_file = os.path.join(tmp_dir, ".git", "info", "sparse-checkout")
        os.makedirs(os.path.dirname(sparse_file), exist_ok=True)
        with open(sparse_file, "w") as f:
            f.write(plugin_path.rstrip("/") + "/\n")

        # Determine which branch(es) to try
        if branch:
            branches_to_try = [branch]
        else:
            branches_to_try = ["main", "master"]

        # Pull from branch
        pull_result = None
        for try_branch in branches_to_try:
            pull_result = subprocess.run(
                ["git", "-C", tmp_dir, "pull", "--depth", "1", "origin", try_branch],
                capture_output=True, text=True, timeout=120
            )
            if pull_result.returncode == 0:
                break

        if pull_result is None or pull_result.returncode != 0:
            stderr = pull_result.stderr.strip() if pull_result else "No branches to try"
            return {"ok": False, "error": f"git pull failed: {stderr}"}

        # Move the subdirectory to target
        src = os.path.join(tmp_dir, plugin_path.replace("/", os.sep))
        if not os.path.isdir(src):
            return {"ok": False, "error": f"Path '{plugin_path}' not found in repo."}

        shutil.move(src, target_dir)

        # Validate
        if not os.path.exists(os.path.join(target_dir, "plugin.json")):
            shutil.rmtree(target_dir, ignore_errors=True)
            return {"ok": False, "error": "Plugin path has no plugin.json."}

        return {"ok": True}

    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def remove_plugin(plugin_id: str) -> dict:
    """Remove a user-installed plugin from usr/plugins/."""
    target_dir = os.path.join(USR_PLUGINS_DIR, plugin_id)

    # Safety: refuse to touch built-in plugins dir
    builtin_dir = files.get_abs_path("plugins", plugin_id)
    if os.path.abspath(target_dir) == os.path.abspath(builtin_dir):
        return {"ok": False, "error": "Cannot uninstall built-in plugins."}

    if not os.path.exists(target_dir):
        return {"ok": False, "error": f"Plugin '{plugin_id}' is not installed in usr/plugins/."}

    try:
        shutil.rmtree(target_dir)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
