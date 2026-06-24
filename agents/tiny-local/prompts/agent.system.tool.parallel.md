### parallel
Run independent tool calls concurrently, or await/cancel background parallel jobs.

Use only when multiple calls are independent and ready now. Each `tool_calls` item is a normal tool request object using only `tool_name` and `tool_args`.

Rules:
- Do not use for one simple call, dependent steps, ordered steps, shared mutable state, or state/tool-availability changes that must happen in the parent context.
- Never nest `parallel`.
- Use `wait:false` only when you will collect results later with `job_ids`.
- If you include `call_subordinate`, set `"profile":"tiny-local"` inside that child call.
- Do not include `thoughts`, `headline`, markdown fences, or prose outside the JSON object.

Args in `tool_args`: `tool_calls`, `job_ids`, `wait`, `action`, `timeout`.

Example:

`{"tool_name":"parallel","tool_args":{"tool_calls":[{"tool_name":"text_editor","tool_args":{"action":"read","path":"/a0/usr/workdir/TODO.md"}},{"tool_name":"call_subordinate","tool_args":{"profile":"tiny-local","message":"Summarize TODO.md in one sentence.","reset":true}}],"wait":true}}`
