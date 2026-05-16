import json
import subprocess

from helpers.api import ApiHandler, Request


class SwarmDiscoverDocker(ApiHandler):
    async def process(self, input: dict, request: Request):
        try:
            proc = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--format",
                    "{{json .}}",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError:
            return {"ok": False, "error": "docker command not found", "candidates": []}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "docker ps timed out", "candidates": []}
        except subprocess.CalledProcessError as exc:
            return {"ok": False, "error": exc.stderr.strip() or str(exc), "candidates": []}

        candidates = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            image = str(item.get("Image") or "")
            names = str(item.get("Names") or "")
            ports = str(item.get("Ports") or "")
            haystack = f"{image} {names}".lower()
            if "agent-zero" not in haystack and "agent0" not in haystack and "a0" not in haystack:
                continue
            candidates.append({
                "label": names or image,
                "container": names,
                "image": image,
                "ports": ports,
                "base_url": "",
            })

        return {"ok": True, "error": "", "candidates": candidates}
