### harness_checkpoint
request an explicit checkpoint before a risky action
use this proactively for installs, destructive commands, protected files, or broad rewrites

usage:
~~~json
{
  "thoughts": [
    "This action is high risk and should be checkpointed before I continue."
  ],
  "headline": "Requesting checkpoint",
  "tool_name": "harness_checkpoint",
  "tool_args": {
    "reason": "Need to install an extra dependency to run the project tests.",
    "proposed_action": "pip install rich",
    "risk_level": "high"
  }
}
~~~
