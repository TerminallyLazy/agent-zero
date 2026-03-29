from __future__ import annotations

import re, json, glob
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    TYPE_CHECKING,
    TypedDict,
)

from python.helpers import files, print_style, yaml as yaml_helper, cache
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from agent import Agent

# Extracts target selector from <meta name="plugin-target" content="...">
_META_TARGET_RE = re.compile(
    r'<meta\s+name=["\']plugin-target["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

type ToggleState = Literal["enabled", "disabled", "advanced"]


class PluginAssetFile(TypedDict):
    path: str
    project_name: str
    agent_profile: str


META_FILE_NAME = "plugin.yaml"
CONFIG_FILE_NAME = "config.json"
CONFIG_DEFAULT_FILE_NAME = "default_config.yaml"
DISABLED_FILE_NAME = ".toggle-0"
ENABLED_FILE_NAME = ".toggle-1"
TOGGLE_FILE_PATTERN = ".toggle-[01]"


class PluginMetadata(BaseModel):
    title: str = ""
    description: str = ""
    version: str = ""
    settings_sections: List[str] = Field(default_factory=list)
    per_project_config: bool = False
    per_agent_config: bool = False
    always_enabled: bool = False


class PluginListItem(BaseModel):
    name: str
    path: str
    display_name: str = ""
    description: str = ""
    version: str = ""
    settings_sections: List[str] = Field(default_factory=list)
    per_project_config: bool = False
    per_agent_config: bool = False
    always_enabled: bool = False
    is_custom: bool = False
    has_main_screen: bool = False
    has_config_screen: bool = False
    has_readme: bool = False
    has_license: bool = False
    has_init_script: bool = False
    toggle_state: ToggleState = "disabled"


def invalidate_plugin_cache():
    cache.clear("*(plugins)*")


def get_plugin_roots(plugin_name: str = "") -> List[str]:
    """Plugin root directories, ordered by priority (user first)."""
    return [
        files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR, plugin_name),
        files.get_abs_path(files.PLUGINS_DIR, plugin_name),
    ]


def get_plugins_list():
    result: list[str] = []
    seen_names: set[str] = set()
    for root in get_plugin_roots():
        for dir in Path(root).iterdir():
            if not dir.is_dir() or dir.name.startswith("."):
                continue
            if dir.name in seen_names:
                continue
            if files.exists(str(dir), META_FILE_NAME):
                seen_names.add(dir.name)
                result.append(dir.name)
    result.sort(key=lambda p: Path(p).name)
    return result


def get_enhanced_plugins_list(
    custom: bool = True, builtin: bool = True
) -> List[PluginListItem]:
    """Discover plugins by directory convention. First root wins on ID conflict."""
    results = []

    def load_plugins(root_path: str, is_custom: bool):
        for d in sorted(Path(root_path).iterdir(), key=lambda p: p.name):
            try:
                if not d.is_dir() or d.name.startswith("."):
                    continue
                meta_file = str(d / META_FILE_NAME)
                if not files.exists(meta_file):
                    continue
                meta = PluginMetadata.model_validate(files.read_file_yaml(meta_file))
                has_main_screen = files.exists(str(d / "webui" / "main.html"))
                has_config_screen = files.exists(str(d / "webui" / "config.html"))
                has_readme = files.exists(str(d / "README.md"))
                has_license = files.exists(str(d / "LICENSE"))
                has_init_script = files.exists(str(d / "initialize.py"))
                toggle_state = get_toggle_state(d.name)
                results.append(
                    PluginListItem(
                        name=d.name,
                        path=str(d),
                        display_name=meta.title or d.name,
                        description=meta.description,
                        version=meta.version,
                        settings_sections=meta.settings_sections,
                        per_project_config=meta.per_project_config,
                        per_agent_config=meta.per_agent_config,
                        always_enabled=meta.always_enabled,
                        is_custom=is_custom,
                        has_main_screen=has_main_screen,
                        has_config_screen=has_config_screen,
                        has_readme=has_readme,
                        has_license=has_license,
                        toggle_state=toggle_state,
                    )
                )
            except Exception as e:
                print_style.PrintStyle.error(f"Failed to load plugin {d.name}: {e}")
                continue

    if custom:
        load_plugins(files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR), True)
    if builtin:
        load_plugins(files.get_abs_path(files.PLUGINS_DIR), False)
    return results


def get_plugin_meta(plugin_name: str):
    plugin_dir = find_plugin_dir(plugin_name)
    if not plugin_dir:
        return None
    return PluginMetadata.model_validate(
        files.read_file_yaml(files.get_abs_path(plugin_dir, META_FILE_NAME))
    )


def find_plugin_dir(plugin_name: str):
    if not plugin_name:
        return None

    # check if the plugin is in the user directory
    user_plugin_path = files.get_abs_path(
        files.USER_DIR, files.PLUGINS_DIR, plugin_name, META_FILE_NAME
    )
    if files.exists(user_plugin_path):
        return files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR, plugin_name)

    # check if the plugin is in the default directory
    default_plugin_path = files.get_abs_path(
        files.PLUGINS_DIR, plugin_name, META_FILE_NAME
    )
    if files.exists(default_plugin_path):
        return files.get_abs_path(files.PLUGINS_DIR, plugin_name)

    return None


def get_plugin_paths(*subpaths: str) -> List[str]:
    sub = "*/" + "/".join(subpaths) if subpaths else "*"
    paths: List[str] = []
    for root in get_plugin_roots():
        paths.extend(
            files.find_existing_paths_by_pattern(files.get_abs_path(root, sub))
        )
    return paths


def get_enabled_plugin_paths(agent: Agent | None, *subpaths: str) -> List[str]:
    enabled = get_enabled_plugins(agent)
    paths: list[str] = []

    for plugin in enabled:
        base_dir = find_plugin_dir(plugin)
        if not base_dir:
            continue

        if not subpaths:
            if files.exists(base_dir):
                paths.append(base_dir)
            continue

        path = files.get_abs_path(base_dir, *subpaths)
        if files.exists(path):
            paths.append(path)

    return paths


def get_enabled_plugins(agent: Agent | None):
    plugins = get_plugins_list()
    active = []

    for plugin in plugins:
        # plugins are toggled via .enabled / .disabled files
        # every plugin is on by default, unless disabled in usr dir
        enabled = True

        # root plugin paths
        plugin_paths = get_plugin_roots(plugin)

        # + agent paths
        if agent:
            from python.helpers import subagents

            agent_paths = subagents.get_paths(
                agent,
                files.PLUGINS_DIR,
                plugin,
                must_exist_completely=True,
                include_default=False,
                include_user=False,
                include_plugins=False,
                include_project=True,
            )
            plugin_paths = agent_paths + plugin_paths

        # go through paths in reverse order and determine the state
        enabled = determined_toggle_from_paths(enabled, reversed(plugin_paths))

        if enabled:
            active.append(plugin)

    return active


def determined_toggle_from_paths(default: bool, paths: Iterator[str]):
    enabled = default
    for plugin_path in paths:
        if enabled:
            enabled = not files.exists(
                files.get_abs_path(plugin_path, DISABLED_FILE_NAME)
            )
        else:
            enabled = files.exists(files.get_abs_path(plugin_path, ENABLED_FILE_NAME))
    return enabled


def get_toggle_state(plugin_name: str) -> ToggleState:
    meta = get_plugin_meta(plugin_name)
    if not meta:
        return "disabled"
    if meta.always_enabled:
        return "enabled"

    # root plugin paths
    plugin_paths = get_plugin_roots(plugin_name)
    state = (
        "enabled"
        if determined_toggle_from_paths(True, reversed(plugin_paths))
        else "disabled"
    )

    # global toggles
    usr_toggles = [
        files.find_existing_paths_by_pattern(
            files.get_abs_path(files.PLUGINS_DIR, plugin_name, TOGGLE_FILE_PATTERN)
        ),
        files.find_existing_paths_by_pattern(
            files.get_abs_path(
                files.USER_DIR, files.PLUGINS_DIR, plugin_name, TOGGLE_FILE_PATTERN
            )
        ),
    ]

    # additional toggles in project/agent directories, return advanced
    if meta.per_agent_config or meta.per_project_config:
        configs = find_plugin_assets(
            TOGGLE_FILE_PATTERN,
            plugin_name=plugin_name,
            project_name="*" if meta.per_project_config else "",
            agent_profile="*" if meta.per_agent_config else "",
            only_first=False,
        )

        # Advanced if there are specific overrides (project or agent specific)
        if any(c.get("project_name") or c.get("agent_profile") for c in configs):
            state = "advanced"

    return state


def toggle_plugin(
    plugin_name: str,
    enabled: bool,
    project_name: str = "",
    agent_profile: str = "",
    clear_overrides: bool = False,
):
    if clear_overrides:
        all_toggles = find_plugin_assets(
            TOGGLE_FILE_PATTERN,
            plugin_name=plugin_name,
            project_name="*",
            agent_profile="*",
            only_first=False,
        )
        for toggle in all_toggles:
            files.delete_file(toggle["path"])

    enabled_file = determine_plugin_asset_path(
        plugin_name, project_name, agent_profile, ENABLED_FILE_NAME
    )
    disabled_file = determine_plugin_asset_path(
        plugin_name, project_name, agent_profile, DISABLED_FILE_NAME
    )

    # ensure clean state by deleting both potential files first
    files.delete_file(enabled_file)
    files.delete_file(disabled_file)

    if enabled:
        files.write_file(enabled_file, "")
    else:
        files.write_file(disabled_file, "")


def get_webui_extensions(extension_point: str, filters: List[str] | None = None):
    entries: List[str] = []
    effective_filters = filters or ["*"]

    for filter in effective_filters:
        extensions = get_plugin_paths("extensions", "webui", extension_point, filter)
        for extension in extensions:
            rel_path = files.deabsolute_path(extension)
            entries.append(rel_path)

    return entries


def get_plugin_config(
    plugin_name: str,
    agent: Agent | None = None,
    project_name: str | None = None,
    agent_profile: str | None = None,
):

    if project_name is None and agent is not None:
        from python.helpers import projects

        project_name = projects.get_context_project_name(agent.context)
    if agent_profile is None and agent is not None:
        agent_profile = agent.config.profile

    # find config.json in all possible places
    file = find_plugin_asset(
        plugin_name,
        CONFIG_FILE_NAME,
        project_name=project_name or "",
        agent_profile=agent_profile or "",
    )
    file_path = file.get("path", "") if file else ""

    # use default config if not found
    if not file_path:
        file_path = files.get_abs_path(
            find_plugin_dir(plugin_name), CONFIG_DEFAULT_FILE_NAME
        )
    if file_path and files.exists(file_path):
        return (
            json.loads if file_path.lower().endswith(".json") else yaml_helper.loads
        )(files.read_file(file_path))
    return None


def save_plugin_config(
    plugin_name: str, project_name: str, agent_profile: str, settings: dict
):
    file_path = determine_plugin_asset_path(
        plugin_name, project_name, agent_profile, CONFIG_FILE_NAME
    )
    if file_path:
        files.write_file(file_path, json.dumps(settings))


def find_plugin_asset(
    plugin_name: str, *subpaths: str, project_name="", agent_profile=""
):
    result = find_plugin_assets(
        *subpaths,
        plugin_name=plugin_name,
        project_name=project_name,
        agent_profile=agent_profile,
        only_first=True,
    )
    return result[0] if result else None


def find_plugin_assets(
    *subpaths: str,
    plugin_name: str = "*",
    project_name: str = "*",
    agent_profile: str = "*",
    only_first: bool = False,
) -> list[PluginAssetFile]:
    from python.helpers import projects, subagents

    results: list[PluginAssetFile] = []

    def _collect(path: str, proj: str, profile: str) -> bool:
        is_glob = glob.has_magic(path)
        matched_paths = (
            files.find_existing_paths_by_pattern(path)
            if is_glob
            else ([path] if files.exists(path) else [])
        )

        need_proj = proj == "*"
        need_prof = profile == "*"

        def _after(s: str, marker: str, last: bool = False) -> str:
            i = s.rfind(marker) if last else s.find(marker)
            if i == -1:
                return ""
            start = i + len(marker)
            end = s.find("/", start)
            return s[start:] if end == -1 else s[start:end]

        for matched in matched_paths:
            inferred_proj = _after(matched, "/projects/") if need_proj else proj
            inferred_prof = (
                _after(matched, "/agents/", last=True) if need_prof else profile
            )
            results.append(
                {
                    "project_name": inferred_proj,
                    "agent_profile": inferred_prof,
                    "path": matched,
                }
            )
            if only_first:
                return True
        return False

    # project/.a0proj/agents/<profile>/plugins/<plugin_name>/...
    if project_name:
        if agent_profile:
            path = projects.get_project_meta(
                project_name,
                files.AGENTS_DIR,
                agent_profile,
                files.PLUGINS_DIR,
                plugin_name,
                *subpaths,
            )
            if _collect(path, project_name, agent_profile):
                return results
        if not agent_profile or agent_profile == "*":
            # project/.a0proj/plugins/<plugin_name>/...
            path = projects.get_project_meta(
                project_name, files.PLUGINS_DIR, plugin_name, *subpaths
            )
            if _collect(path, project_name, ""):
                return results

    # usr/agents/<profile>/plugins/<plugin_name>/...
    if agent_profile:
        path = files.get_abs_path(
            subagents.USER_AGENTS_DIR,
            agent_profile,
            files.PLUGINS_DIR,
            plugin_name,
            *subpaths,
        )
        if _collect(path, "", agent_profile):
            return results

        # usr?/plugins/<any_plugin>/agents/<profile>/plugins/<plugin_name>/...
        for plugin_base in get_enabled_plugin_paths(None):
            path = files.get_abs_path(
                plugin_base,
                files.AGENTS_DIR,
                agent_profile,
                files.PLUGINS_DIR,
                plugin_name,
                *subpaths,
            )
            if _collect(path, "", agent_profile):
                return results

        # agents/<profile>/plugins/<plugin_name>/...
        path = files.get_abs_path(
            subagents.DEFAULT_AGENTS_DIR,
            agent_profile,
            files.PLUGINS_DIR,
            plugin_name,
            *subpaths,
        )
        if _collect(path, "", agent_profile):
            return results

    # usr/plugins/<plugin_name>/...
    path = files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR, plugin_name, *subpaths)
    if _collect(path, "", ""):
        return results

    # plugins/<plugin_name>/...
    path = files.get_abs_path(files.PLUGINS_DIR, plugin_name, *subpaths)
    _collect(path, "", "")

    return results


def determine_plugin_asset_path(
    plugin_name: str, project_name: str, agent_profile: str, *subpaths: str
):
    base_path = files.get_abs_path(files.USER_DIR)

    if project_name:
        from python.helpers import projects

        base_path = projects.get_project_meta(project_name)

    if agent_profile:
        base_path = files.get_abs_path(base_path, files.AGENTS_DIR, agent_profile)

    return files.get_abs_path(base_path, files.PLUGINS_DIR, plugin_name, *subpaths)
