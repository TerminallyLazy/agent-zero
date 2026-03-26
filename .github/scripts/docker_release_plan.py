#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_SYSTEM_PROMPT_PATH = REPO_ROOT / "scripts" / "openrouter_release_notes_system_prompt.md"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}<<__EOF__\n{value}\n__EOF__\n")


def write_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path or not lines:
        return
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write("## Docker publish plan\n\n")
        for line in lines:
            handle.write(f"- {line}\n")


def run_command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True)
    if check and result.returncode != 0:
        command = " ".join(args)
        fail(f"Command failed ({command}):\n{result.stderr.strip()}")
    return result


def git(*args: str, check: bool = True) -> str:
    return run_command("git", *args, check=check).stdout.strip()


def docker_tag_exists(image_repo: str, tag: str) -> bool:
    result = run_command(
        "docker",
        "buildx",
        "imagetools",
        "inspect",
        f"{image_repo}:{tag}",
        check=False,
    )
    return result.returncode == 0


def split_branches(raw: str) -> list[str]:
    parts = re.split(r"[\s,]+", raw.strip())
    return [part for part in parts if part]


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        fail(f"Required environment variable `{name}` is missing.")
    return value


def require_any_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    fail(
        "Required environment variable is missing. Expected one of: "
        + ", ".join(f"`{name}`" for name in names)
    )


@dataclass(frozen=True)
class Config:
    allowed_branches: list[str]
    main_branch: str
    image_repo: str
    tag_pattern: re.Pattern[str]
    min_version: tuple[int, int]
    event_name: str
    source_ref_name: str
    source_ref_type: str
    manual_tag: str
    before_sha: str
    after_sha: str


@dataclass(frozen=True)
class BranchState:
    branch: str
    valid_tags: list[str]
    latest_tag: str | None


@dataclass
class Candidate:
    branch: str
    source_tag: str
    mode: str
    publish_version: bool
    publish_branch_tag: bool
    reason: str


@dataclass(frozen=True)
class CommitEntry:
    heading: str
    description: str


def load_config() -> Config:
    allowed_branches = split_branches(os.environ["ALLOWED_BRANCHES"])
    if not allowed_branches:
        fail("ALLOWED_BRANCHES must not be empty.")
    main_branch = os.environ["MAIN_BRANCH"].strip()
    if main_branch not in allowed_branches:
        fail("MAIN_BRANCH must also be listed in ALLOWED_BRANCHES.")

    tag_regex = os.environ["RELEASE_TAG_REGEX"]
    return Config(
        allowed_branches=allowed_branches,
        main_branch=main_branch,
        image_repo=os.environ["DOCKER_IMAGE_REPO"].strip(),
        tag_pattern=re.compile(tag_regex),
        min_version=(
            int(os.environ["MIN_RELEASE_MAJOR"]),
            int(os.environ["MIN_RELEASE_MINOR"]),
        ),
        event_name=os.environ["EVENT_NAME"].strip(),
        source_ref_name=os.environ.get("SOURCE_REF_NAME", "").strip(),
        source_ref_type=os.environ.get("SOURCE_REF_TYPE", "").strip(),
        manual_tag=os.environ.get("MANUAL_TAG", "").strip(),
        before_sha=os.environ.get("BEFORE_SHA", "").strip(),
        after_sha=os.environ.get("AFTER_SHA", "").strip(),
    )


def parse_release_tag(config: Config, tag: str) -> tuple[int, int] | None:
    match = config.tag_pattern.fullmatch(tag)
    if not match:
        return None
    version = (int(match.group(1)), int(match.group(2)))
    if version < config.min_version:
        return None
    return version


def tag_exists(tag: str) -> bool:
    return run_command("git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}", check=False).returncode == 0


def tag_commit(tag: str) -> str:
    return git("rev-list", "-n", "1", f"refs/tags/{tag}")


def commit_is_ancestor(older_ref: str, newer_ref: str) -> bool:
    return (
        run_command(
            "git",
            "merge-base",
            "--is-ancestor",
            older_ref,
            newer_ref,
            check=False,
        ).returncode
        == 0
    )


def branch_contains_commit(branch: str, commit: str) -> bool:
    return (
        run_command(
            "git",
            "merge-base",
            "--is-ancestor",
            commit,
            f"origin/{branch}",
            check=False,
        ).returncode
        == 0
    )


def ref_exists(ref: str) -> bool:
    if not ref or re.fullmatch(r"0{40}", ref):
        return False
    return run_command("git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).returncode == 0


def releasable_tags_for_ref(config: Config, ref: str) -> list[str]:
    if not ref_exists(ref):
        return []

    tagged_versions: list[tuple[tuple[int, int], str]] = []
    merged_tags = git("tag", "--merged", ref)
    for tag in merged_tags.splitlines():
        version = parse_release_tag(config, tag.strip())
        if version is None:
            continue
        tagged_versions.append((version, tag.strip()))

    tagged_versions.sort(key=lambda item: item[0])
    return [tag for _, tag in tagged_versions]


def latest_releasable_tag_for_ref(config: Config, ref: str) -> str | None:
    valid_tags = releasable_tags_for_ref(config, ref)
    return valid_tags[-1] if valid_tags else None


def collect_branch_states(config: Config, branches: list[str] | None = None) -> dict[str, BranchState]:
    states: dict[str, BranchState] = {}
    for branch in branches or config.allowed_branches:
        if run_command("git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}", check=False).returncode != 0:
            fail(f"Allowed branch origin/{branch} was not fetched.")

        valid_tags = releasable_tags_for_ref(config, f"origin/{branch}")
        states[branch] = BranchState(
            branch=branch,
            valid_tags=valid_tags,
            latest_tag=valid_tags[-1] if valid_tags else None,
        )
    return states


def add_or_merge_candidate(candidates: dict[tuple[str, str, str], Candidate], candidate: Candidate) -> None:
    key = (candidate.branch, candidate.source_tag, candidate.mode)
    existing = candidates.get(key)
    if existing is None:
        candidates[key] = candidate
        return
    existing.publish_version = existing.publish_version or candidate.publish_version
    existing.publish_branch_tag = existing.publish_branch_tag or candidate.publish_branch_tag
    if candidate.reason not in existing.reason:
        existing.reason = f"{existing.reason}; {candidate.reason}"


def plan_tag_push(config: Config, branch_states: dict[str, BranchState]) -> tuple[list[Candidate], list[str]]:
    source_tag = config.source_ref_name
    notes: list[str] = []
    version = parse_release_tag(config, source_tag)
    if version is None:
        return [], [f"Skipped `{source_tag}` because it does not match `v{{X}}.{{Y}}` or is below v{config.min_version[0]}.{config.min_version[1]}."]
    if not tag_exists(source_tag):
        return [], [f"Skipped `{source_tag}` because the tag is not present after checkout."]

    commit = tag_commit(source_tag)
    candidates: list[Candidate] = []
    found_branch = False
    for branch, state in branch_states.items():
        if not branch_contains_commit(branch, commit):
            continue
        found_branch = True
        if state.latest_tag != source_tag:
            notes.append(
                f"Skipped `{source_tag}` on `{branch}` because `{state.latest_tag}` is the highest release tag currently reachable from that branch."
            )
            continue
        candidates.append(
            Candidate(
                branch=branch,
                source_tag=source_tag,
                mode="push_latest_only",
                publish_version=branch == config.main_branch,
                publish_branch_tag=True,
                reason=f"Automatic build for the latest release tag on `{branch}`.",
            )
        )

    if not found_branch:
        notes.append(f"Skipped `{source_tag}` because it is not reachable from any allowed branch.")
    return candidates, notes


def plan_branch_push(config: Config, branch_states: dict[str, BranchState]) -> tuple[list[Candidate], list[str]]:
    branch = config.source_ref_name
    if branch not in branch_states:
        return [], [f"Skipped `{branch}` because it is not an allowed release branch."]

    before_tag = latest_releasable_tag_for_ref(config, config.before_sha)
    after_tag = branch_states[branch].latest_tag
    if after_tag is None:
        return [], [f"Skipped `{branch}` because it has no releasable tags."]
    if before_tag == after_tag:
        return [], [f"Skipped `{branch}` because its highest release tag is still `{after_tag}`."]

    return [
        Candidate(
            branch=branch,
            source_tag=after_tag,
            mode="push_promoted_tag",
            publish_version=branch == config.main_branch,
            publish_branch_tag=True,
            reason=f"Automatic build for `{after_tag}` after it reached `{branch}`.",
        )
    ], []


def plan_manual_exact(config: Config, branch_states: dict[str, BranchState]) -> tuple[list[Candidate], list[str]]:
    manual_tag = config.manual_tag
    if parse_release_tag(config, manual_tag) is None:
        fail(
            f"Manual tag `{manual_tag}` is invalid. Expected `v{{X}}.{{Y}}` with a minimum of v{config.min_version[0]}.{config.min_version[1]}."
        )
    if not tag_exists(manual_tag):
        fail(f"Manual tag `{manual_tag}` does not exist in the repository.")

    commit = tag_commit(manual_tag)
    notes: list[str] = []
    candidates: list[Candidate] = []
    for branch, state in branch_states.items():
        if not branch_contains_commit(branch, commit):
            continue
        if branch == config.main_branch:
            candidates.append(
                Candidate(
                    branch=branch,
                    source_tag=manual_tag,
                    mode="manual_exact",
                    publish_version=True,
                    publish_branch_tag=state.latest_tag == manual_tag,
                    reason=f"Manual rebuild for `{manual_tag}` on `{branch}`.",
                )
            )
            continue
        if state.latest_tag != manual_tag:
            notes.append(
                f"Skipped `{manual_tag}` on `{branch}` because non-main branches only publish their current branch tag and `{state.latest_tag}` is newer."
            )
            continue
        candidates.append(
            Candidate(
                branch=branch,
                source_tag=manual_tag,
                mode="manual_exact",
                publish_version=False,
                publish_branch_tag=True,
                reason=f"Manual rebuild for the current branch image on `{branch}`.",
            )
        )

    if not candidates:
        notes.append(f"No eligible images were found for manual tag `{manual_tag}`.")
    return candidates, notes


def plan_manual_backfill(config: Config, branch_states: dict[str, BranchState]) -> tuple[list[Candidate], list[str]]:
    notes: list[str] = []
    candidates: dict[tuple[str, str, str], Candidate] = {}

    for branch, state in branch_states.items():
        if not state.valid_tags:
            notes.append(f"Branch `{branch}` has no releasable tags.")
            continue

        if branch == config.main_branch:
            for tag in state.valid_tags:
                if docker_tag_exists(config.image_repo, tag):
                    continue
                add_or_merge_candidate(
                    candidates,
                    Candidate(
                        branch=branch,
                        source_tag=tag,
                        mode="manual_backfill",
                        publish_version=True,
                        publish_branch_tag=False,
                        reason=f"Missing Docker Hub tag `{tag}`.",
                    ),
                )

            latest_tag = state.latest_tag
            if latest_tag and not docker_tag_exists(config.image_repo, "latest"):
                add_or_merge_candidate(
                    candidates,
                    Candidate(
                        branch=branch,
                        source_tag=latest_tag,
                        mode="manual_backfill",
                        publish_version=False,
                        publish_branch_tag=True,
                        reason="Missing Docker Hub tag `latest`.",
                    ),
                )
            continue

        if not docker_tag_exists(config.image_repo, branch):
            add_or_merge_candidate(
                candidates,
                Candidate(
                    branch=branch,
                    source_tag=state.latest_tag,
                    mode="manual_backfill",
                    publish_version=False,
                    publish_branch_tag=True,
                    reason=f"Missing Docker Hub tag `{branch}`.",
                ),
            )

    if not candidates:
        notes.append("No missing Docker Hub tags were found.")
    return list(candidates.values()), notes


def plan_command() -> None:
    config = load_config()
    branch_states = collect_branch_states(config)

    if config.event_name == "workflow_dispatch":
        if config.manual_tag:
            candidates, notes = plan_manual_exact(config, branch_states)
        else:
            candidates, notes = plan_manual_backfill(config, branch_states)
    elif config.event_name == "push":
        if config.source_ref_type == "tag":
            candidates, notes = plan_tag_push(config, branch_states)
        elif config.source_ref_type == "branch":
            candidates, notes = plan_branch_push(config, branch_states)
        else:
            fail(f"Unsupported push ref type: {config.source_ref_type}")
    else:
        fail(f"Unsupported event: {config.event_name}")

    summary_lines = [candidate.reason for candidate in candidates]
    summary_lines.extend(notes)

    matrix = {"include": [asdict(candidate) for candidate in candidates]}
    write_output("has_work", "true" if candidates else "false")
    write_output("matrix", json.dumps(matrix))
    write_summary(summary_lines)

    print(json.dumps(matrix, indent=2))
    for line in summary_lines:
        print(f"- {line}")


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def load_text(path: Path) -> str:
    if not path.exists():
        fail(f"Expected file `{path}` to exist.")
    return path.read_text(encoding="utf-8").strip()


def github_repository_parts() -> tuple[str, str]:
    repository = require_env("GITHUB_REPOSITORY")
    owner, separator, repo = repository.partition("/")
    if not owner or not separator or not repo:
        fail(f"GITHUB_REPOSITORY must be in `owner/repo` format, got `{repository}`.")
    return owner, repo


def github_api_get(path: str, params: dict[str, str | int] | None = None) -> object:
    api_base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    token = require_env("GITHUB_TOKEN")
    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{api_base}{path}{query}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        fail(f"GitHub API request failed ({path}): {exc.code} {exc.reason}\n{details}")
    except URLError as exc:
        fail(f"GitHub API request failed ({path}): {exc.reason}")


def list_github_releases() -> list[dict[str, object]]:
    owner, repo = github_repository_parts()
    releases: list[dict[str, object]] = []
    page = 1

    while True:
        payload = github_api_get(
            f"/repos/{owner}/{repo}/releases",
            {"per_page": 100, "page": page},
        )
        if not isinstance(payload, list):
            fail("GitHub releases response was not a list.")
        page_items = [item for item in payload if isinstance(item, dict)]
        releases.extend(page_items)
        if len(page_items) < 100:
            break
        page += 1

    return releases


def previous_published_release_tag(config: Config, source_tag: str) -> str | None:
    source_version = parse_release_tag(config, source_tag)
    if source_version is None:
        fail(f"Tag `{source_tag}` is not a releasable tag.")

    previous: list[tuple[tuple[int, int], str]] = []
    for release in list_github_releases():
        if release.get("draft") or release.get("prerelease"):
            continue
        tag_name = str(release.get("tag_name", "")).strip()
        version = parse_release_tag(config, tag_name)
        if version is None or version >= source_version:
            continue
        previous.append((version, tag_name))

    previous.sort(key=lambda item: item[0])
    return previous[-1][1] if previous else None


def parse_commit_entries(raw_log: str) -> list[CommitEntry]:
    entries: list[CommitEntry] = []
    for raw_entry in raw_log.split("\x1e"):
        entry = raw_entry.strip()
        if not entry:
            continue
        heading, separator, description = entry.partition("\x1f")
        if not separator:
            continue
        entries.append(
            CommitEntry(
                heading=re.sub(r"\s+", " ", heading).strip(),
                description=description.strip(),
            )
        )
    return entries


def collect_release_commits(previous_release_tag: str | None, source_tag: str) -> list[CommitEntry]:
    range_ref = source_tag
    if previous_release_tag:
        if not tag_exists(previous_release_tag):
            fail(f"Previous published release tag `{previous_release_tag}` is not available in the repository.")
        if not commit_is_ancestor(
            f"refs/tags/{previous_release_tag}^{{commit}}",
            f"refs/tags/{source_tag}^{{commit}}",
        ):
            fail(
                f"Previous published release tag `{previous_release_tag}` is not an ancestor of `{source_tag}`."
            )
        range_ref = f"{previous_release_tag}..{source_tag}"

    raw_log = git("log", "--reverse", "--format=%s%x1f%b%x1e", range_ref)
    return parse_commit_entries(raw_log)


def build_release_notes_user_message(commits: list[CommitEntry]) -> str:
    lines = ["Commit headings and descriptions:"]

    if not commits:
        lines.append("No commits were found in this release range.")
        return "\n".join(lines)

    for index, commit in enumerate(commits, start=1):
        lines.append(f"{index}. Heading: {commit.heading}")
        if commit.description:
            lines.append("Description:")
            lines.append(commit.description)
        else:
            lines.append("Description: (none)")
        lines.append("")

    return "\n".join(lines).strip()


def extract_openrouter_message_content(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""

    content = payload.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def generate_release_body_with_openrouter(commits: list[CommitEntry]) -> str:
    api_key = require_env("OPENROUTER_API_KEY")
    model = require_any_env("OPENROUTER_MODEL_NAME", "OPENROUTER_MODEL")
    system_prompt = load_text(OPENROUTER_SYSTEM_PROMPT_PATH)
    repository = require_env("GITHUB_REPOSITORY")
    user_message = build_release_notes_user_message(commits)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
    }
    request = Request(
        OPENROUTER_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": f"https://github.com/{repository}",
            "X-OpenRouter-Title": "Agent Zero Docker Release Notes",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        fail(f"OpenRouter request failed: {exc.code} {exc.reason}\n{details}")
    except URLError as exc:
        fail(f"OpenRouter request failed: {exc.reason}")

    if not isinstance(response_payload, dict):
        fail("OpenRouter response was not a JSON object.")

    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        fail(f"OpenRouter response did not include choices: {json.dumps(response_payload)}")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        fail("OpenRouter returned an invalid choice payload.")

    message = first_choice.get("message")
    body = extract_openrouter_message_content(message).strip()
    return body or "No release notes."


def resolve_release_command() -> None:
    config = load_config()
    branch = os.environ["TARGET_BRANCH"].strip()
    source_tag = os.environ["TARGET_TAG"].strip()

    if branch != config.main_branch:
        write_output("should_release", "false")
        write_output("skip_reason", f"Branch `{branch}` does not publish GitHub releases.")
        return

    branch_state = collect_branch_states(config, [branch])[branch]
    if branch_state.latest_tag is None:
        write_output("should_release", "false")
        write_output("skip_reason", f"Branch `{branch}` has no releasable tags.")
        return

    if parse_release_tag(config, source_tag) is None or not tag_exists(source_tag):
        write_output("should_release", "false")
        write_output("skip_reason", f"Tag `{source_tag}` is not a releasable tag.")
        return

    commit = tag_commit(source_tag)
    if not branch_contains_commit(branch, commit):
        write_output("should_release", "false")
        write_output("skip_reason", f"Tag `{source_tag}` is no longer reachable from `{branch}`.")
        return

    if branch_state.latest_tag != source_tag:
        write_output("should_release", "false")
        write_output(
            "skip_reason",
            f"Tag `{source_tag}` is not the highest release tag on `{branch}`.",
        )
        return

    previous_release_tag = ""
    commits: list[CommitEntry] = []
    body = "Failed to generate release notes."
    try:
        previous_release_tag = previous_published_release_tag(config, source_tag) or ""
        commits = collect_release_commits(previous_release_tag or None, source_tag)
        body = generate_release_body_with_openrouter(commits)
    except SystemExit:
        print(
            f"Release note generation failed for `{source_tag}`. Falling back to a static release body.",
            file=sys.stderr,
        )
    except Exception as exc:
        print(
            f"Unexpected release note generation error for `{source_tag}`: {exc}. Falling back to a static release body.",
            file=sys.stderr,
        )

    write_output("should_release", "true")
    write_output("release_tag", source_tag)
    write_output("release_name", source_tag)
    write_output("previous_release_tag", previous_release_tag)
    write_output("release_commit_count", str(len(commits)))
    write_output("release_body", body)
    print(source_tag)


def resolve_build_command() -> None:
    config = load_config()
    branch = os.environ["TARGET_BRANCH"].strip()
    source_tag = os.environ["TARGET_TAG"].strip()
    mode = os.environ["TARGET_MODE"].strip()
    publish_version = os.environ["TARGET_PUBLISH_VERSION"].strip().lower() == "true"
    publish_branch_tag = os.environ["TARGET_PUBLISH_BRANCH_TAG"].strip().lower() == "true"

    branch_state = collect_branch_states(config, [branch])[branch]
    if branch_state.latest_tag is None:
        write_output("should_build", "false")
        write_output("skip_reason", f"Branch `{branch}` has no releasable tags.")
        return

    if parse_release_tag(config, source_tag) is None or not tag_exists(source_tag):
        write_output("should_build", "false")
        write_output("skip_reason", f"Tag `{source_tag}` is no longer available.")
        return

    commit = tag_commit(source_tag)
    if not branch_contains_commit(branch, commit):
        write_output("should_build", "false")
        write_output("skip_reason", f"Tag `{source_tag}` is no longer reachable from `{branch}`.")
        return

    mutable_tag = "latest" if branch == config.main_branch else branch
    tags_to_push: list[str] = []

    if mode == "push_latest_only":
        if branch_state.latest_tag != source_tag:
            write_output("should_build", "false")
            write_output(
                "skip_reason",
                f"Tag `{source_tag}` is no longer the highest release tag on `{branch}`.",
            )
            return
        if publish_version:
            tags_to_push.append(f"{config.image_repo}:{source_tag}")
        if publish_branch_tag:
            tags_to_push.append(f"{config.image_repo}:{mutable_tag}")

    elif mode == "push_promoted_tag":
        if branch_state.latest_tag != source_tag:
            write_output("should_build", "false")
            write_output(
                "skip_reason",
                f"Tag `{source_tag}` is no longer the highest release tag on `{branch}`.",
            )
            return
        if publish_version and not docker_tag_exists(config.image_repo, source_tag):
            tags_to_push.append(f"{config.image_repo}:{source_tag}")
        if publish_branch_tag:
            tags_to_push.append(f"{config.image_repo}:{mutable_tag}")

    elif mode == "manual_exact":
        if publish_version:
            tags_to_push.append(f"{config.image_repo}:{source_tag}")
        if publish_branch_tag and branch_state.latest_tag == source_tag:
            tags_to_push.append(f"{config.image_repo}:{mutable_tag}")

    elif mode == "manual_backfill":
        if publish_version and not docker_tag_exists(config.image_repo, source_tag):
            tags_to_push.append(f"{config.image_repo}:{source_tag}")
        if publish_branch_tag:
            if branch != config.main_branch and branch_state.latest_tag != source_tag:
                write_output("should_build", "false")
                write_output(
                    "skip_reason",
                    f"Tag `{source_tag}` is no longer the newest release tag on `{branch}`.",
                )
                return
            if branch == config.main_branch and branch_state.latest_tag != source_tag:
                publish_branch_tag = False
            if publish_branch_tag and not docker_tag_exists(config.image_repo, mutable_tag):
                tags_to_push.append(f"{config.image_repo}:{mutable_tag}")
    else:
        fail(f"Unsupported resolve-build mode: {mode}")

    tags_to_push = unique(tags_to_push)
    if not tags_to_push:
        write_output("should_build", "false")
        write_output("skip_reason", "All requested Docker tags already exist or are no longer eligible.")
        return

    write_output("should_build", "true")
    write_output("tags", "\n".join(tags_to_push))
    write_output("display_tags", ", ".join(tag.rsplit(":", 1)[1] for tag in tags_to_push))
    print("\n".join(tags_to_push))


def main() -> None:
    if len(sys.argv) != 2:
        fail("Usage: docker_release_plan.py <plan|resolve-build|resolve-release>")

    command = sys.argv[1]
    if command == "plan":
        plan_command()
        return
    if command == "resolve-build":
        resolve_build_command()
        return
    if command == "resolve-release":
        resolve_release_command()
        return
    fail(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
