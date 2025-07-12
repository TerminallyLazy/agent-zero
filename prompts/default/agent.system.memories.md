# Memories on the topic
- following are memories about current topic
- do not overly rely on them they might not be relevant
{{#if memory_backend}}
- Memory backend: {{memory_backend}}
{{#if memory_count}}
- {{memory_count}} memories retrieved
{{/if}}
{{#eq memory_backend "MemOS"}}
- Enhanced memories with metadata filtering and relevance scoring
{{/eq}}
{{/if}}

{{memories}}