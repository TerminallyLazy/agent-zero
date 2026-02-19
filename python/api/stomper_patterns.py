import re
import time

from python.helpers.api import ApiHandler, Input, Output, Request


def _test_regex_performance(compiled: re.Pattern, timeout: float = 0.5) -> float | None:
    """Test a compiled regex against a pathological string. Returns elapsed time, or None if safe."""
    test_str = "a" * 1000
    start = time.time()
    try:
        compiled.search(test_str)
    except Exception:
        pass
    elapsed = time.time() - start
    return elapsed if elapsed > timeout else None


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
                compiled = re.compile(regex)
            except re.error as e:
                return {"error": f"Invalid regex: {str(e)}"}

            # ReDoS safety: test against pathological input
            slow_time = _test_regex_performance(compiled)
            if slow_time is not None:
                return {"error": f"Regex is too slow ({slow_time:.1f}s on test input). Avoid nested quantifiers."}

            weight = max(0.0, min(1.0, weight))
            try:
                pattern = registry.add_custom_pattern(name, category, attack_type, regex, weight)
            except ValueError as e:
                return {"error": str(e)}
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
                # ReDoS safety check
                slow_time = _test_regex_performance(compiled)
                if slow_time is not None:
                    return {"matches": False, "error": f"Regex is too slow ({slow_time:.1f}s on test input). Avoid nested quantifiers."}
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
