"""
Eden API - Policies Endpoint

GET /eden/policies - List all policies
POST /eden/policies - Create or update policies
DELETE /eden/policies/:id - Delete a policy
"""

from datetime import datetime
from typing import Optional
import uuid

try:
    from python.helpers.api import ApiHandler
except ImportError:
    class ApiHandler:
        @classmethod
        def requires_auth(cls) -> bool:
            return True

from python.helpers.eden.models import Policy
from python.helpers.eden.policy_engine import get_engine


class PoliciesHandler(ApiHandler):
    """Handle policy configuration requests."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST", "DELETE"]

    async def process(self, input: dict, request) -> dict:
        """Route policy requests."""
        method = request.method
        policy_id = input.get("id")

        if method == "GET":
            return await self._list_policies()

        elif method == "POST":
            return await self._create_or_update_policies(input)

        elif method == "DELETE":
            if policy_id:
                return await self._delete_policy(policy_id)
            return {"error": "Policy ID required"}, 400

        return {"error": "Method not allowed"}, 405

    async def _list_policies(self) -> dict:
        """List all policies."""
        engine = get_engine()

        policies = engine.export_policies()
        suggestions = engine.suggest_refinements()

        return {
            "policies": policies,
            "count": len(policies),
            "suggestions": suggestions,
        }

    async def _create_or_update_policies(self, input: dict) -> dict:
        """Create or update policies from text."""
        engine = get_engine()

        # Accept either single policy text or array of policies
        policy_text = input.get("policies", "")
        if isinstance(policy_text, str):
            # Split by newlines, filter empty
            policy_lines = [
                line.strip()
                for line in policy_text.strip().split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
        else:
            policy_lines = policy_text

        # Clear existing and add new
        # In production, you'd want to merge/update
        engine.policies.clear()

        added = []
        for line in policy_lines:
            policy = engine.add_policy(line)
            if policy:
                added.append({
                    "id": policy.id,
                    "text": policy.original_text,
                    "trigger": policy.trigger,
                    "action": policy.action,
                })

        return {
            "success": True,
            "policies": added,
            "count": len(added),
            "message": f"Added {len(added)} policies",
        }

    async def _delete_policy(self, policy_id: str) -> dict:
        """Delete a policy."""
        engine = get_engine()

        if engine.remove_policy(policy_id):
            return {
                "success": True,
                "message": f"Policy {policy_id} deleted",
            }
        else:
            return {"error": "Policy not found"}, 404


# Handler for /eden/policies endpoint
Policies = PoliciesHandler
