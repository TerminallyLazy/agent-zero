from __future__ import annotations

import json
import shutil
from pathlib import Path

from usr.plugins.agent_harness.helpers.models import WorkspacePaths

WORKSPACE_ROOT = ".harness"
GITIGNORE_ENTRIES = [".harness/workspace/", ".harness/offloads/"]


def ensure_workspace(project_dir: str) -> WorkspacePaths:
    root = Path(project_dir) / WORKSPACE_ROOT
    paths = WorkspacePaths(
        root=str(root),
        workspace=str(root / "workspace"),
        outputs=str(root / "outputs"),
        offloads=str(root / "offloads"),
        runs=str(root / "runs"),
    )
    for p in [paths.workspace, paths.outputs, paths.offloads, paths.runs]:
        Path(p).mkdir(parents=True, exist_ok=True)
    return paths


def ensure_gitignore(project_dir: str) -> None:
    gitignore_path = Path(project_dir) / ".gitignore"
    existing = gitignore_path.read_text() if gitignore_path.exists() else ""
    lines_to_add = [e for e in GITIGNORE_ENTRIES if e not in existing]
    if lines_to_add:
        suffix = "\n" if existing and not existing.endswith("\n") else ""
        gitignore_path.write_text(
            existing + suffix + "\n".join(lines_to_add) + "\n"
        )


def sub_task_workspace(paths: WorkspacePaths, sub_task_id: str) -> str:
    p = Path(paths.workspace) / sub_task_id
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def write_offload(paths: WorkspacePaths, offload_id: str, content: str) -> str:
    filepath = Path(paths.offloads) / f"{offload_id}.md"
    filepath.write_text(content)
    return str(filepath)


def write_run_log(paths: WorkspacePaths, run_data: dict) -> str:
    filepath = Path(paths.runs) / f"{run_data.get('run_id', 'unknown')}.json"
    filepath.write_text(json.dumps(run_data, indent=2))
    return str(filepath)


def clean_workspace(paths: WorkspacePaths) -> None:
    for p in [paths.workspace, paths.offloads]:
        if Path(p).exists():
            shutil.rmtree(p)
