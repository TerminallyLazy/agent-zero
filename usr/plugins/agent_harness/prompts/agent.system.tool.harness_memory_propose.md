### harness_memory_propose
propose a reusable repo convention or lesson for later review
use this when a stable rule would help future runs in the same repo or agent profile

usage:
~~~json
{
  "thoughts": [
    "This repo preference is stable enough to remember for later."
  ],
  "headline": "Proposing harness memory",
  "tool_name": "harness_memory_propose",
  "tool_args": {
    "rule_text": "Run file-scoped pytest first before the full suite.",
    "reason": "It keeps verification loops fast in this repository.",
    "scope": "project",
    "confidence": 0.9
  }
}
~~~
