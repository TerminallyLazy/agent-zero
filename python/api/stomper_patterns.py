import re

from python.helpers.api import ApiHandler, Input, Output, Request


class StomperPatterns(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        from plugins.prompt_stomper.helpers.scanner import get_registry

        registry = get_registry()
        action = input.get("action", "list")

        if action == "list":
            patterns = registry.get_all_patterns()
            return {
                "patterns": [
                    {
                        "name": p.name,
                        "category": p.category,
                        "attack_type": p.attack_type,
                        "regex": p.regex,
                        "weight": p.weight,
                        "enabled": p.enabled,
                        "builtin": p.builtin,
                    }
                    for p in patterns
                ]
            }

        elif action == "add":
            name = input.get("name", "").strip()
            category = input.get("category", "").strip()
            attack_type = input.get("attack_type", "direct")
            regex = input.get("regex", "").strip()
            weight = float(input.get("weight", 0.5))

            if not name or not regex:
                return {"error": "name and regex are required"}

            # Validate regex
            try:
                re.compile(regex)
            except re.error as e:
                return {"error": f"Invalid regex: {str(e)}"}

            weight = max(0.0, min(1.0, weight))
            pattern = registry.add_custom_pattern(name, category, attack_type, regex, weight)
            return {"status": "added", "pattern": {"name": pattern.name, "category": pattern.category}}

        elif action == "remove":
            name = input.get("name", "").strip()
            if not name:
                return {"error": "name is required"}
            removed = registry.remove_custom_pattern(name)
            return {"status": "removed" if removed else "not_found"}

        elif action == "toggle":
            name = input.get("name", "").strip()
            enabled = input.get("enabled", True)
            found = registry.toggle_pattern(name, enabled)
            return {"status": "toggled" if found else "not_found"}

        elif action == "test":
            text = input.get("text", "")
            regex = input.get("regex", "")
            if not regex:
                return {"matches": False, "error": "No regex provided"}
            try:
                compiled = re.compile(regex)
                match = compiled.search(text)
                return {
                    "matches": bool(match),
                    "matched_text": match.group(0) if match else None,
                }
            except re.error as e:
                return {"matches": False, "error": str(e)}

        return {"error": "Unknown action"}

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]
