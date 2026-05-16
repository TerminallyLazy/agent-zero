### swarm_message
Send a message to the orchestrator or to a peer subagent in the same swarm run. Use it to report blockers, ask questions, share intermediate results, or coordinate with peers. Only available to subagents spawned by `delegate_parallel`.

A successful call means the message was accepted into the swarm ledger; the response includes the delivery state: `queued` (accepted, not yet delivered), `delivered` (target received it), or `failed` (with the reason). Peer messages are only allowed inside the same swarm run.

Args:
- `recipient` (string, required): `"orchestrator"` or a peer agent name such as `"SA1_2"`.
- `content` (string, required): the message content.
- `is_blocker` (bool, optional): set `true` only when you cannot continue without help; this marks the sender BLOCKED.

Use `recipient="orchestrator"` for blockers, status updates, and decisions that need parent-agent input.

Example:
~~~json
{
  "thoughts": ["I need the API key from the orchestrator before I can continue."],
  "tool_name": "swarm_message",
  "tool_args": {
    "recipient": "orchestrator",
    "content": "I need the OpenAI API key to proceed with the embedding step.",
    "is_blocker": true
  }
}
~~~
