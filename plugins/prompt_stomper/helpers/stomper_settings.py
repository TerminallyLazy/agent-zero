"""Settings management for Prompt Stomper.

Stored in usr/prompt_stomper/settings.json, separate from the main
Agent Zero settings to avoid coupling.
"""

import json
import os
import threading

from python.helpers import files


SETTINGS_FILE = files.get_abs_path("usr", "prompt_stomper", "settings.json")

DEFAULT_SETTINGS = {
    "enabled": True,
    "scan_user_messages": True,
    "scan_tool_outputs": True,
    "system_hardening": True,
    "canary_tokens": True,
    "block_action": "block",       # "block", "warn", "log"
    "sensitivity": 1.0,            # multiplier for score thresholds
}


_lock = threading.RLock()
_settings: dict | None = None


def get_settings() -> dict:
    global _settings
    with _lock:
        if _settings is None:
            _settings = _load_settings()
        return dict(_settings)


def set_settings(updates: dict) -> dict:
    global _settings
    with _lock:
        current = get_settings()
        # Only accept known keys
        for key in DEFAULT_SETTINGS:
            if key in updates:
                current[key] = updates[key]
        _settings = current
        _save_settings(current)
        return dict(current)


def _load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
            settings.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS})
        except (json.JSONDecodeError, IOError):
            pass
    return settings


def _save_settings(settings: dict):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
