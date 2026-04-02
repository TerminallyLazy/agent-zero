from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from usr.plugins.agent_harness.helpers.models import WorkspacePaths

WORKSPACE_ROOT = ".harness"
GITIGNORE_ENTRIES = [".harness/workspace/", ".harness/offloads/", ".harness/threads/"]


def _safe_context_segment(context_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in context_id)


def ensure_workspace(project_dir: str, context_id: str = "") -> WorkspacePaths:
    root = Path(project_dir) / WORKSPACE_ROOT
    thread_root = root / "threads" / _safe_context_segment(context_id) if context_id else None
    user_data = thread_root / "user-data" if thread_root else None
    workspace_dir = user_data / "workspace" if user_data else root / "workspace"
    outputs_dir = user_data / "outputs" if user_data else root / "outputs"
    uploads_dir = user_data / "uploads" if user_data else root / "uploads"
    paths = WorkspacePaths(
        root=str(root),
        workspace=str(workspace_dir),
        outputs=str(outputs_dir),
        uploads=str(uploads_dir),
        offloads=str(root / "offloads"),
        runs=str(root / "runs"),
        thread_root=str(thread_root) if thread_root else "",
        user_data=str(user_data) if user_data else "",
    )
    for p in [paths.workspace, paths.outputs, paths.uploads, paths.offloads, paths.runs]:
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


def save_upload(paths: WorkspacePaths, filename: str, content: bytes) -> str:
    filepath = Path(paths.uploads) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_bytes(content)
    return str(filepath)


def list_uploads(paths: WorkspacePaths) -> list[dict[str, Any]]:
    uploads_root = Path(paths.uploads)
    if not uploads_root.exists():
        return []
    results: list[dict[str, Any]] = []
    for file_path in sorted(p for p in uploads_root.rglob("*") if p.is_file()):
        relative = file_path.relative_to(uploads_root).as_posix()
        results.append(
            {
                "name": file_path.name,
                "path": relative,
                "abs_path": str(file_path),
                "size": file_path.stat().st_size,
            }
        )
    return results


def delete_upload(paths: WorkspacePaths, relative_path: str) -> bool:
    target = resolve_upload(paths, relative_path, create_parent=False)
    if not target.exists() or not target.is_file():
        return False
    target.unlink()
    return True


def resolve_upload(
    paths: WorkspacePaths,
    relative_path: str,
    *,
    create_parent: bool = False,
) -> Path:
    uploads_root = Path(paths.uploads).resolve()
    candidate = (uploads_root / relative_path).resolve()
    if uploads_root != candidate and uploads_root not in candidate.parents:
        raise ValueError("Upload path escapes the thread uploads directory")
    if create_parent:
        candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def list_artifacts(paths: WorkspacePaths) -> list[dict[str, Any]]:
    outputs_root = Path(paths.outputs)
    if not outputs_root.exists():
        return []
    results: list[dict[str, Any]] = []
    for file_path in sorted(p for p in outputs_root.rglob("*") if p.is_file()):
        relative = file_path.relative_to(outputs_root).as_posix()
        results.append(
            {
                "name": file_path.name,
                "path": relative,
                "abs_path": str(file_path),
                "size": file_path.stat().st_size,
            }
        )
    return results


def resolve_artifact(paths: WorkspacePaths, relative_path: str) -> Path:
    outputs_root = Path(paths.outputs).resolve()
    candidate = (outputs_root / relative_path).resolve()
    if outputs_root != candidate and outputs_root not in candidate.parents:
        raise ValueError("Artifact path escapes the thread outputs directory")
    return candidate


def cleanup_thread_data(paths: WorkspacePaths) -> None:
    if paths.thread_root and Path(paths.thread_root).exists():
        shutil.rmtree(paths.thread_root)
