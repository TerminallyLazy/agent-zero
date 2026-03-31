### harness_checkpoint
request a mandatory checkpoint before risky actions — the user must approve before you proceed

#### WHEN TO USE (MANDATORY — do not skip):
- Before running pip install, npm install, apt-get install, or any package manager
- Before git push, git reset --hard, or any destructive git operation
- Before rm -rf or any recursive file deletion
- Before modifying files in protected paths (agent.py, initialize.py, usr/plugins/)
- Before any action that cannot be easily undone

If you skip a checkpoint for a risky action, the guardrails will block you automatically.
It is better to checkpoint proactively than to be blocked reactively.

usage:
~~~json
{
  "thoughts": [
    "I need to install a dependency. This requires user approval first."
  ],
  "headline": "Requesting checkpoint before dependency install",
  "tool_name": "harness_checkpoint",
  "tool_args": {
    "reason": "Need to install the 'rich' library for terminal formatting.",
    "proposed_action": "pip install rich",
    "risk_level": "high"
  }
}
~~~
