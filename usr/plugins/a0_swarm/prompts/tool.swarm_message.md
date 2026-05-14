### swarm_message
Send a message to another swarm agent or to the orchestrator. Use this to report blockers, ask questions, share intermediate results, or coordinate with peers.

**Args:**
- `recipient` (string): Target agent name (e.g. "SA1_2") or "orchestrator"
- `content` (string): The message content
- `is_blocker` (bool, optional): Set true if you are blocked and need help before continuing

**Example — reporting a blocker:**
```json
{
  "thoughts": ["I need the API key from the orchestrator before I can continue."],
  "tool_name": "swarm_message",
  "tool_args": {
    "recipient": "orchestrator",
    "content": "I need the OpenAI API key to proceed with the embedding step.",
    "is_blocker": true
  }
}
```
