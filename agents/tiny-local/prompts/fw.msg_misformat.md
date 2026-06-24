/no_think

Your last message was not valid JSON for a tool request.

Reply now with exactly one JSON object and nothing else.

Valid fallback if unsure:
`{"tool_name":"response","tool_args":{"text":"I need a valid next action to continue."}}`

If your invalid text described an action, convert it to the matching tool call.

Example:
Invalid: `I will inspect TODO.md now.`
Valid: `{"tool_name":"text_editor","tool_args":{"action":"read","path":"/a0/usr/workdir/TODO.md"}}`

Rules:
- Use only `tool_name` and `tool_args` as top-level fields.
- Do not include `thoughts`, `headline`, markdown fences, apologies, or explanations.
- Do not repeat the invalid text.
- Do not describe what you will do. Call the tool.
