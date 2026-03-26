import subprocess
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.modules["giturlparse"] = types.SimpleNamespace(
    parse=lambda *args, **kwargs: types.SimpleNamespace(
        owner="",
        repo="",
        name="",
        valid=False,
    )
)

from helpers import git


def run_git(repo_dir: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def init_repo_with_tag(repo_dir: Path, branch: str) -> None:
    run_git(repo_dir, "init")
    run_git(repo_dir, "branch", "-m", branch)
    run_git(repo_dir, "config", "user.name", "Test User")
    run_git(repo_dir, "config", "user.email", "test@example.com")
    (repo_dir / "tracked.txt").write_text("one\n", encoding="utf-8")
    run_git(repo_dir, "add", "tracked.txt")
    run_git(repo_dir, "commit", "-m", "initial")
    run_git(repo_dir, "tag", "v1.9")


def add_commit(repo_dir: Path, content: str) -> None:
    (repo_dir / "tracked.txt").write_text(content, encoding="utf-8")
    run_git(repo_dir, "add", "tracked.txt")
    run_git(repo_dir, "commit", "-m", "update")


def test_git_version_label_shows_commit_distance_on_development(tmp_path):
    init_repo_with_tag(tmp_path, "development")
    add_commit(tmp_path, "two\n")

    info = git.get_repo_release_info(str(tmp_path))

    assert info.release is not None
    assert info.release.short_tag == "v1.9"
    assert info.release.version == "D v1.9+1"


def test_git_version_label_hides_commit_distance_on_main(tmp_path):
    init_repo_with_tag(tmp_path, "main")
    add_commit(tmp_path, "two\n")

    info = git.get_repo_release_info(str(tmp_path))

    assert info.release is not None
    assert info.release.short_tag == "v1.9"
    assert info.release.version == "M v1.9"
