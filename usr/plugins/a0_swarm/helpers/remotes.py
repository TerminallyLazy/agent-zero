"""
Remote A0 endpoint resolution for a0_swarm.

Plugin config schema (default_config.yaml / saved config):

    remotes:
      - label: "research-rig"
        base_url: "http://a0-research:55000"
        auth_token: "..."
      - label: "code-runner"
        base_url: "http://a0-code:55000"
        auth_token: ""

`label` is the user-facing handle that delegate_parallel tasks reference
via `endpoint: "<label>"`. `base_url` may also be passed directly as the
endpoint when no label match is found.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    from helpers import plugins as _framework_plugins
except Exception:  # pragma: no cover - test stub path
    _framework_plugins = None  # type: ignore


PLUGIN_NAME = "a0_swarm"


@dataclass
class RemoteEndpoint:
    label: str
    base_url: str
    auth_token: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "RemoteEndpoint":
        return cls(
            label=str(raw.get("label", "")).strip(),
            base_url=str(raw.get("base_url", "")).strip(),
            auth_token=str(raw.get("auth_token", "")).strip(),
        )

    def is_valid(self) -> bool:
        return bool(self.label and self.base_url)


def load_remotes(agent=None) -> list[RemoteEndpoint]:
    """Return the list of configured remotes for the given agent context."""
    if _framework_plugins is None:
        return []
    try:
        cfg = _framework_plugins.get_plugin_config(PLUGIN_NAME, agent=agent) or {}
    except Exception:
        return []
    raw_list = cfg.get("remotes") or []
    if not isinstance(raw_list, list):
        return []
    remotes = [RemoteEndpoint.from_dict(r) for r in raw_list if isinstance(r, dict)]
    return [r for r in remotes if r.is_valid()]


def resolve_endpoint(endpoint: str, agent=None) -> Optional[RemoteEndpoint]:
    """Resolve a task's `endpoint` value to a RemoteEndpoint.

    Matches by label first, then by exact base_url. Returns None if the
    string looks like a raw URL (http(s)://...) with no config match — the
    caller can still construct a RemoteEndpoint directly from it without
    auth.
    """
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return None
    remotes = load_remotes(agent=agent)
    for r in remotes:
        if r.label == endpoint or r.base_url == endpoint:
            return r
    if endpoint.startswith(("http://", "https://")):
        return RemoteEndpoint(label=endpoint, base_url=endpoint, auth_token="")
    return None
