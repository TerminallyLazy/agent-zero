"""Thin wrapper for Prompt Stomper scan_content tool.

Delegates to plugins/prompt_stomper/tools/scan_content.py.
This wrapper exists because the tool loader only scans python/tools/.
Remove this when the plugin system adds plugin tool loading.
"""

from plugins.prompt_stomper.tools.scan_content import ScanContent  # noqa: F401
