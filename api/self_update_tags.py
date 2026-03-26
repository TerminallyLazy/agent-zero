from helpers.api import ApiHandler, Request, Response

from helpers import runtime
from helpers import self_update


class SelfUpdateTags(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        branch = str(input.get("branch", "")).strip().lower()
        current_branch = self_update.get_repo_version_info().get("branch", "").strip().lower()
        available_branch_values = self_update.get_available_branch_values()
        if current_branch in available_branch_values:
            default_branch = current_branch
        elif "main" in available_branch_values:
            default_branch = "main"
        elif available_branch_values:
            default_branch = available_branch_values[0]
        else:
            default_branch = "main"
        resolved_branch = branch or default_branch

        try:
            tag_options, higher_major_versions, error = self_update.get_selector_tag_options(
                resolved_branch,
            )
            return {
                "success": True,
                "supported": runtime.is_dockerized(),
                "branch": resolved_branch,
                "tags": [option["value"] for option in tag_options],
                "tag_options": tag_options,
                "higher_major_versions": higher_major_versions,
                "error": error,
            }
        except Exception as e:
            return {
                "success": False,
                "supported": runtime.is_dockerized(),
                "branch": resolved_branch,
                "tags": [],
                "tag_options": [],
                "higher_major_versions": [],
                "error": str(e),
            }
