from __future__ import annotations

from pathlib import Path

from helpers.skills_import import ConflictPolicy, ImportResult, import_skills

DEFAULT_NAMESPACE = "deerflow"


def _normalize_path(source_path: str | Path) -> Path:
    path = Path(source_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _looks_like_public_skills_root(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any((child / "SKILL.md").is_file() for child in path.iterdir() if child.is_dir())


def resolve_public_skills_root(source_path: str | Path) -> Path:
    source = _normalize_path(source_path)
    candidates = (
        source / "skills" / "public",
        source / "public",
        source,
    )

    for candidate in candidates:
        if _looks_like_public_skills_root(candidate):
            return candidate.resolve()

    raise FileNotFoundError(
        "Could not find a DeerFlow public skills directory. "
        "Expected <repo>/skills/public, <skills>/public, or a direct public skills path."
    )


def list_public_skills(source_path: str | Path) -> list[str]:
    public_root = resolve_public_skills_root(source_path)
    skills = [
        child.name
        for child in public_root.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    ]
    skills.sort()
    return skills


def import_public_skills(
    source_path: str | Path,
    *,
    namespace: str = DEFAULT_NAMESPACE,
    conflict: ConflictPolicy = "skip",
    project_name: str | None = None,
    agent_profile: str | None = None,
) -> ImportResult:
    public_root = resolve_public_skills_root(source_path)
    return import_skills(
        str(public_root),
        namespace=namespace,
        conflict=conflict,
        dry_run=False,
        project_name=project_name,
        agent_profile=agent_profile,
    )


def collect_plugin_asset_status(plugin_root: str | Path) -> dict[str, bool]:
    root = _normalize_path(plugin_root)
    expected = {
        "install_doc": root / "Install.md",
        "check_script": root / "scripts" / "check_deerflow_harness.py",
        "import_script": root / "scripts" / "import_deerflow_public_skills.py",
        "bootstrap_skill": root / "skills" / "public" / "bootstrap" / "SKILL.md",
        "find_skills_skill": root / "skills" / "public" / "find-skills" / "SKILL.md",
    }
    return {name: path.is_file() for name, path in expected.items()}
