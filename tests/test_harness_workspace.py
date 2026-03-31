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
    assert Path(paths.offloads).exists()
    assert Path(paths.runs).exists()


def test_ensure_workspace_is_idempotent(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import ensure_workspace
    paths1 = ensure_workspace(str(tmp_path))
    paths2 = ensure_workspace(str(tmp_path))
    assert paths1.root == paths2.root


def test_ensure_gitignore_adds_entries(tmp_path):
    from usr.plugins.agent_harness.helpers.workspace import ensure_gitignore
    ensure_gitignore(str(tmp_path))
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".harness/workspace/" in gitignore
    assert ".harness/offloads/" in gitignore
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
