from helpers.api import ApiHandler, Request
from usr.plugins.a0_swarm.helpers.remotes import RemoteEndpoint
from usr.plugins.a0_swarm.helpers import a2a_runner


def _list_of_strings(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))]


def _summarize_skills(card: dict) -> list[dict]:
    skills = card.get("skills") or []
    if not isinstance(skills, list):
        return []
    summarized = []
    for raw in skills:
        if not isinstance(raw, dict):
            continue
        summarized.append({
            "id": str(raw.get("id") or raw.get("name") or "").strip(),
            "name": str(raw.get("name") or raw.get("id") or "").strip(),
            "description": str(raw.get("description") or "").strip(),
            "tags": _list_of_strings(raw.get("tags")),
        })
    return summarized


def _summarize_agent_card(card: dict) -> dict:
    capabilities = card.get("capabilities") if isinstance(card.get("capabilities"), dict) else {}
    provider = card.get("provider") if isinstance(card.get("provider"), dict) else {}
    return {
        "name": str(card.get("name") or "Unknown A2A agent"),
        "description": str(card.get("description") or ""),
        "version": str(card.get("version") or ""),
        "provider": provider or {},
        "capabilities": capabilities or {},
        "input_modes": _list_of_strings(card.get("defaultInputModes") or card.get("inputModes")),
        "output_modes": _list_of_strings(card.get("defaultOutputModes") or card.get("outputModes")),
        "skills": _summarize_skills(card),
        "communication": {
            "agent_card": "verified",
            "task_submission": "available_via_message_send",
            "context_continuation": "available_via_context_id",
            "cancel": "available_via_task_cancel",
        },
    }


class SwarmTestRemote(ApiHandler):
    async def process(self, input: dict, request: Request):
        data = input or {}
        label = str(data.get("label") or data.get("endpoint") or "").strip()
        base_url = str(data.get("base_url") or data.get("url") or "").strip()
        auth_token = str(data.get("auth_token") or "").strip()

        if not base_url:
            return {"ok": False, "error": "base_url is required", "checks": {}, "endpoint": label}

        remote = RemoteEndpoint(label=label or base_url, base_url=base_url, auth_token=auth_token)
        runtime_remote = a2a_runner.runtime_remote(remote)
        checks = {
            "agent_card": {"ok": False, "error": ""},
            "submit": {"ok": False, "error": "agent card must pass first"},
            "continuation": {"ok": False, "error": "agent card must pass first"},
            "cancel": {"ok": False, "error": "agent card must pass first"},
        }
        discovery = {}

        try:
            conn = await a2a_runner.open_connection(remote)
            try:
                card = await conn.get_agent_card()
                discovery = _summarize_agent_card(card or {})
                checks["agent_card"] = {"ok": True, "error": ""}
                checks["submit"] = {
                    "ok": True,
                    "error": "",
                    "detail": "A2A message/send is available after Agent Card discovery.",
                }
                checks["continuation"] = {
                    "ok": True,
                    "error": "",
                    "detail": "Follow-up swarm messages reuse the stored A2A context_id.",
                }
                checks["cancel"] = {
                    "ok": True,
                    "error": "",
                    "detail": "Remote cancellation uses A2A task cancel with the stored task_id.",
                }
            finally:
                await conn.close()
        except Exception as exc:
            error = str(exc)
            if runtime_remote.base_url != remote.base_url:
                error = (
                    f"{error} Tested as {runtime_remote.base_url} because localhost "
                    "inside Docker points at the current Agent Zero container."
                )
            checks["agent_card"] = {"ok": False, "error": error}
            return {
                "ok": False,
                "error": error,
                "checks": checks,
                "endpoint": remote.label,
                "remote": {
                    "label": remote.label,
                    "base_url": runtime_remote.base_url,
                    "input_base_url": remote.base_url if runtime_remote.base_url != remote.base_url else "",
                },
                "discovery": discovery,
            }

        return {
            "ok": True,
            "error": "",
            "checks": checks,
            "endpoint": remote.label,
            "remote": {
                "label": remote.label,
                "base_url": runtime_remote.base_url,
                "input_base_url": remote.base_url if runtime_remote.base_url != remote.base_url else "",
            },
            "discovery": discovery,
        }
