from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_ensure_workspace_creates_directories(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import ensure_workspace
    paths = ensure_workspace(str(tmp_path))
    assert Path(paths.workspace).exists()
    assert Path(paths.outputs).exists()
    assert Path(paths.uploads).exists()
    assert Path(paths.offloads).exists()
    assert Path(paths.runs).exists()


def test_ensure_workspace_is_idempotent(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import ensure_workspace
    paths1 = ensure_workspace(str(tmp_path), context_id="ctx-1")
    paths2 = ensure_workspace(str(tmp_path), context_id="ctx-1")
    assert paths1.root == paths2.root
    assert paths1.thread_root == paths2.thread_root


def test_ensure_workspace_with_context_creates_thread_data_dirs(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import ensure_workspace
    paths = ensure_workspace(str(tmp_path), context_id="ctx:thread")
    assert Path(paths.thread_root).exists()
    assert Path(paths.user_data).exists()
    assert Path(paths.workspace).exists()
    assert Path(paths.outputs).exists()
    assert Path(paths.uploads).exists()
    assert Path(paths.workspace).as_posix().endswith(
        "/threads/ctx_thread/user-data/workspace"
    )


def test_ensure_gitignore_adds_entries(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import ensure_gitignore
    ensure_gitignore(str(tmp_path))
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".harness/workspace/" in gitignore
    assert ".harness/offloads/" in gitignore
    assert ".harness/threads/" in gitignore
    # Idempotent — should not duplicate
    ensure_gitignore(str(tmp_path))
    gitignore2 = (tmp_path / ".gitignore").read_text()
    assert gitignore2.count(".harness/workspace/") == 1


def test_write_offload_creates_file(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import ensure_workspace, write_offload
    paths = ensure_workspace(str(tmp_path))
    filepath = write_offload(paths, "off_123", "Some long content here")
    assert Path(filepath).exists()
    assert Path(filepath).read_text() == "Some long content here"


def test_clean_workspace_removes_temp_dirs(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import ensure_workspace, clean_workspace
    paths = ensure_workspace(str(tmp_path))
    (Path(paths.workspace) / "test.txt").write_text("temp")
    (Path(paths.offloads) / "test.txt").write_text("temp")
    (Path(paths.outputs) / "result.txt").write_text("keep")
    clean_workspace(paths)
    assert not Path(paths.workspace).exists()
    assert not Path(paths.offloads).exists()
    assert Path(paths.outputs).exists()
    assert Path(paths.runs).exists()


def test_upload_and_artifact_helpers_respect_thread_boundaries(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import (
        delete_upload,
        ensure_workspace,
        list_artifacts,
        list_uploads,
        resolve_artifact,
        save_upload,
    )

    paths = ensure_workspace(str(tmp_path), context_id="ctx-uploads")
    save_upload(paths, "notes.txt", b"hello")
    uploads = list_uploads(paths)
    assert uploads[0]["path"] == "notes.txt"
    assert delete_upload(paths, "notes.txt") is True
    assert list_uploads(paths) == []

    artifact = Path(paths.outputs) / "report.txt"
    artifact.write_text("artifact")
    artifacts = list_artifacts(paths)
    assert artifacts[0]["path"] == "report.txt"
    assert resolve_artifact(paths, "report.txt") == artifact.resolve()


def test_cleanup_thread_data_removes_only_thread_root(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import cleanup_thread_data, ensure_workspace

    paths = ensure_workspace(str(tmp_path), context_id="ctx-cleanup")
    (Path(paths.workspace) / "scratch.txt").write_text("temp")
    cleanup_thread_data(paths)
    assert not Path(paths.thread_root).exists()
    assert Path(paths.offloads).exists()
    assert Path(paths.runs).exists()
