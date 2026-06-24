### call_subordinate
Delegate only when a separate child agent is truly needed.

Args in `tool_args`:
- `message`: concrete role, goal, and task for the child agent
- `profile`: use `"tiny-local"` for this profile
- `reset`: use JSON boolean `true` for the first child message or when changing task

Rules:
- Prefer doing simple work yourself with the available tools.
- If you call a subordinate, include `"profile":"tiny-local"` so the child uses the same compact JSON-only prompts.
- Do not use default, researcher, developer, hacker, or other long profiles unless the user explicitly asks for that profile.
- After the subordinate returns a sufficient result, answer from that result directly.
- Do not include `thoughts`, `headline`, markdown fences, or prose outside the JSON object.

Example:

`{"tool_name":"call_subordinate","tool_args":{"profile":"tiny-local","message":"Inspect TODO.md and return the next unchecked item only.","reset":true}}`

{{if agent_profiles}}
Available profiles:
{{agent_profiles}}
{{endif}}
