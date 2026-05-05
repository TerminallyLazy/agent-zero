"""POST /api/plugins/jcode_harness/purge_imported_profiles.

Removes all ``_a0_imported_*`` provider profiles from
``~/.jcode/config.toml``. Spike 0.9 verified jcode has no
``provider remove`` subcommand, so the harness edits the TOML directly
through ``provider_import.purge_imported_profiles``.
"""

from __future__ import annotations

from helpers.api import ApiHandler, Request


class PurgeImported(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        from usr.plugins.jcode_harness.helpers.daemon import (
            locate_jcode_binary,
        )
        from usr.plugins.jcode_harness.helpers.provider_import import (
            purge_imported_profiles,
        )

        bin_path = locate_jcode_binary()
        if not bin_path:
            return {"ok": False, "error": "jcode not installed", "purged": []}
        try:
            purged = purge_imported_profiles(bin_path)
            return {"ok": True, "purged": purged}
        except Exception as e:  # noqa: BLE001 — surface any failure to UI
            return {"ok": False, "error": str(e), "purged": []}
