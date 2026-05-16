# swarm_message

Use `swarm_message` when you are an `a0_swarm` subagent and need to communicate with the orchestrator or a peer in the same swarm run.

Arguments:

- `recipient`: `"orchestrator"` or a peer agent name such as `"SA1_2"`.
- `content`: the message to send.
- `is_blocker`: set to `true` only when you cannot continue without help.

Rules:

- Peer messages are only allowed inside the same swarm run.
- A successful tool call means the message was accepted into the swarm ledger.
- The tool response includes delivery state. `queued` means accepted but not yet delivered. `delivered` means the target received the message. `failed` includes the delivery reason.
- Use `recipient="orchestrator"` for blockers, status updates, and decisions that need parent-agent input.
