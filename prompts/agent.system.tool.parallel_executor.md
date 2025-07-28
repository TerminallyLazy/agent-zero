# Parallel Executor Tool

Execute multiple operations concurrently with built-in concurrency control and error handling.

## Tool Name
`parallel_executor`

## Description
The parallel executor tool allows you to run multiple operations simultaneously, significantly improving performance for tasks that can be parallelized. It uses asyncio.TaskGroup for robust parallel execution and integrates with Agent Zero's concurrency limiting system to prevent rate limit violations.

## Use Cases
- Execute multiple LLM calls concurrently
- Communicate with multiple agents simultaneously
- Run multiple tool operations in parallel
- Batch processing of similar tasks
- Performance optimization for independent operations

## Arguments

### Required Arguments
- `operations` (string/array): JSON array of operation definitions or comma-separated list of simple operations

### Optional Arguments
- `max_concurrency` (number, default: 5): Maximum number of concurrent operations
- `timeout` (number, default: 60.0): Timeout for all operations in seconds
- `fail_fast` (boolean, default: false): Whether to stop execution on first error

## Operation Types

### Simple Operations
For testing and basic parallel execution:
```json
{
  "type": "simple",
  "data": "operation description",
  "delay": 0.1
}
```

### Agent Calls
For communicating with subordinate agents:
```json
{
  "type": "agent_call",
  "message": "task for subordinate agent",
  "agent_id": "optional_agent_identifier"
}
```

### LLM Calls
For direct language model interactions:
```json
{
  "type": "llm_call",
  "prompt": "prompt for the language model",
  "model": "optional_model_name"
}
```

### Tool Calls
For calling other Agent Zero tools:
```json
{
  "type": "tool_call",
  "tool_name": "name_of_tool",
  "args": {"key": "value"}
}
```

## Usage Examples

### Basic Parallel Execution
```json
{
  "tool_name": "parallel_executor",
  "tool_args": {
    "operations": "[{\"type\": \"simple\", \"data\": \"task1\"}, {\"type\": \"simple\", \"data\": \"task2\"}]",
    "max_concurrency": 3
  }
}
```

### Simple String Format
```json
{
  "tool_name": "parallel_executor",
  "tool_args": {
    "operations": "search web for AI news, check weather forecast, generate summary"
  }
}
```

### Multiple Agent Calls
```json
{
  "tool_name": "parallel_executor",
  "tool_args": {
    "operations": "[{\"type\": \"agent_call\", \"message\": \"research AI trends\"}, {\"type\": \"agent_call\", \"message\": \"analyze market data\"}]",
    "max_concurrency": 2,
    "timeout": 120
  }
}
```

### Mixed Operations with Error Handling
```json
{
  "tool_name": "parallel_executor",
  "tool_args": {
    "operations": "[{\"type\": \"llm_call\", \"prompt\": \"summarize document\"}, {\"type\": \"tool_call\", \"tool_name\": \"knowledge_tool\", \"args\": {\"query\": \"latest research\"}}]",
    "fail_fast": "false",
    "timeout": 60
  }
}
```

## Response Format

The tool returns a JSON response with detailed execution statistics:

```json
{
  "total_operations": 3,
  "successful": 2,
  "failed": 1,
  "total_duration": 2.456,
  "results": [
    {
      "index": 0,
      "success": true,
      "result": "operation result",
      "duration": 1.234
    },
    {
      "index": 1,
      "success": false,
      "error": "operation failed",
      "duration": 0.567
    }
  ],
  "errors": [
    {
      "index": 1,
      "error": "detailed error message"
    }
  ]
}
```

## Best Practices

1. **Concurrency Control**: Set appropriate `max_concurrency` based on rate limits and system resources
2. **Timeout Management**: Use reasonable timeout values to prevent hanging operations
3. **Error Handling**: Set `fail_fast: false` for resilient execution when some failures are acceptable
4. **Performance**: Use parallel execution for independent operations that don't depend on each other's results
5. **Rate Limiting**: The tool automatically respects existing rate limits and concurrency controls

## Performance Benefits

The parallel executor can significantly improve performance:
- Multiple LLM calls: 60-80% time reduction
- Agent communications: Linear speedup with number of agents
- Mixed operations: Optimal resource utilization

## Error Handling

The tool provides robust error handling:
- Individual operation failures don't stop other operations (unless `fail_fast` is true)
- Detailed error reporting for debugging
- Timeout protection for long-running operations
- Graceful degradation under resource constraints

## Integration Notes

- Integrates with Agent Zero's existing concurrency limiting system
- Respects rate limits configured for different providers
- Compatible with all existing Agent Zero tools and patterns
- Thread-safe and async-compatible