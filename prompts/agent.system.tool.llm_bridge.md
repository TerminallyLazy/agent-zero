# LLM Bridge Tool

Execute LLM calls with concurrency control and optional remote agent delegation.

## Tool Name
`llm_bridge`

## Description
The LLM bridge tool provides a unified interface for making language model calls, supporting both local LiteLLM calls and remote agent delegation. It includes built-in concurrency limiting to prevent rate limit violations and seamless integration with Agent Zero's existing model infrastructure.

## Key Features
- **Concurrency Control**: Automatic rate limiting based on provider settings
- **Remote Delegation**: Route LLM calls to remote agents via ACP/A2A protocols
- **Unified Interface**: Consistent API for both local and remote LLM access
- **Streaming Support**: Real-time response streaming for better user experience
- **Token Tracking**: Automatic token usage monitoring and reporting

## Use Cases
- Make LLM calls with automatic concurrency management
- Delegate compute-intensive LLM tasks to remote agents
- Access specialized models hosted on remote systems
- Implement distributed LLM processing across multiple agents
- Batch process multiple LLM requests efficiently

## Arguments

### Required Arguments
- `prompt` (string): The user prompt/message for the LLM

### Optional Arguments
- `system_message` (string, default: ""): System message to guide the LLM
- `model` (string): Specific model name to use (overrides agent default)
- `provider` (string): Provider name (overrides agent default)
- `remote_agent` (string): Remote agent endpoint for delegation
- `max_tokens` (number): Maximum tokens to generate
- `temperature` (number, default: 0.7): Temperature for generation (0.0 to 2.0)
- `stream` (boolean, default: true): Whether to stream the response
- `timeout` (number, default: 60): Request timeout in seconds
- `format` (string, default: "simple"): Response format ("simple" or "detailed")

## Usage Examples

### Basic Local LLM Call
```json
{
  "tool_name": "llm_bridge",
  "tool_args": {
    "prompt": "Explain quantum computing in simple terms",
    "system_message": "You are a helpful science educator"
  }
}
```

### Specific Model and Provider
```json
{
  "tool_name": "llm_bridge",
  "tool_args": {
    "prompt": "Write a Python function to calculate fibonacci numbers",
    "model": "gpt-4",
    "provider": "openai",
    "max_tokens": 500,
    "temperature": 0.3
  }
}
```

### Remote Agent Delegation
```json
{
  "tool_name": "llm_bridge",
  "tool_args": {
    "prompt": "Analyze this large dataset and provide insights",
    "remote_agent": "https://analysis-agent.example.com",
    "model": "claude-3-opus",
    "timeout": 120
  }
}
```

### Detailed Response Format
```json
{
  "tool_name": "llm_bridge",
  "tool_args": {
    "prompt": "Generate a creative story about AI",
    "system_message": "You are a creative writing assistant",
    "format": "detailed",
    "temperature": 1.2
  }
}
```

### Non-streaming Call
```json
{
  "tool_name": "llm_bridge",
  "tool_args": {
    "prompt": "What is 2+2?",
    "stream": "false",
    "max_tokens": 10
  }
}
```

## Response Formats

### Simple Format (Default)
Returns just the LLM response text:
```
Quantum computing is a revolutionary computing paradigm that leverages the principles of quantum mechanics...
```

### Detailed Format
Returns structured JSON with metadata:
```json
{
  "response": "Quantum computing is a revolutionary computing paradigm...",
  "model_used": "gpt-4",
  "provider": "openai",
  "source": "local",
  "tokens_used": 245,
  "duration": 2.341,
  "reasoning": "The user asked for a simple explanation, so I focused on..."
}
```

### Remote Agent Response
```json
{
  "response": "Based on the dataset analysis, I found three key insights...",
  "model_used": "claude-3-opus",
  "provider": "remote",
  "source": "remote",
  "remote_agent": "https://analysis-agent.example.com",
  "tokens_used": 1250,
  "duration": 15.678
}
```

## Concurrency Management

The tool automatically applies concurrency limits based on the provider:

| Provider | Max Concurrent | Rate Limit Strategy |
|----------|----------------|-------------------|
| OpenAI | 10 | Token bucket with backoff |
| Anthropic | 5 | Conservative limiting |
| OpenRouter | 8 | Moderate concurrency |
| Local Models | 3 | Resource-aware limiting |
| Remote Agents | 5 | Network-aware limiting |
| Other | 5 | Default conservative limit |

## Remote Agent Integration

When using `remote_agent`, the tool:

1. **Discovers Protocol**: Automatically detects ACP or A2A protocol
2. **Formats Request**: Converts parameters to protocol-specific format
3. **Handles Authentication**: Uses agent's configured credentials
4. **Manages Sessions**: Maintains connections for efficiency
5. **Error Recovery**: Falls back to local LLM if remote fails

### Remote Call Parameters
The tool sends these parameters to remote agents:
- `prompt`: User prompt text
- `system_message`: System guidance (if provided)
- `model`: Requested model name (if specified)
- `max_tokens`: Token limit (if specified)
- `temperature`: Generation temperature (if specified)

## Performance Optimization

### Streaming Benefits
- **Real-time Feedback**: Users see responses as they're generated
- **Reduced Latency**: Perceived faster response times
- **Better UX**: Progress indication for long responses

### Concurrency Benefits
- **Rate Limit Compliance**: Prevents API violations
- **Resource Management**: Optimizes system utilization
- **Parallel Processing**: Multiple calls execute simultaneously

### Caching and Sessions
- **Connection Reuse**: HTTP connections are pooled
- **Agent Discovery Cache**: Remote agent capabilities cached
- **Token Estimation**: Efficient token counting

## Error Handling

The tool handles various error conditions:

### Local LLM Errors
- API rate limits and quotas
- Model availability issues
- Network connectivity problems
- Invalid parameters or formats

### Remote Agent Errors
- Agent discovery failures
- Protocol compatibility issues
- Remote agent unavailability
- Authentication and authorization errors

### Example Error Responses
```
Error: Remote LLM call failed: Agent not responding
Error: prompt parameter is required
Error: Cannot discover remote agent at invalid-url.com
```

## Best Practices

1. **Use Appropriate Models**: Select models based on task complexity
2. **Set Reasonable Timeouts**: Balance responsiveness with success rates
3. **Monitor Token Usage**: Track costs and optimize prompts
4. **Leverage Remote Agents**: Use for specialized or compute-intensive tasks
5. **Handle Errors Gracefully**: Implement fallback strategies
6. **Optimize Concurrency**: Don't exceed provider limits
7. **Cache Results**: Store responses for repeated queries

## Integration with Other Tools

### With ParallelExecutor
```json
{
  "tool_name": "parallel_executor",
  "tool_args": {
    "operations": "[
      {\"type\": \"llm_call\", \"prompt\": \"Summarize document A\"},
      {\"type\": \"llm_call\", \"prompt\": \"Summarize document B\"}
    ]"
  }
}
```

### With Agent Bridge
The LLM bridge automatically uses the agent bridge for remote calls, providing seamless protocol abstraction.

## Security Considerations

- **API Key Management**: Uses Agent Zero's secure credential handling
- **Input Validation**: Sanitizes prompts and parameters
- **Network Security**: HTTPS-only for remote communications
- **Rate Limiting**: Prevents abuse and resource exhaustion
- **Error Information**: Minimal exposure of internal details

## Troubleshooting

### Common Issues
1. **"Prompt parameter is required"**: Ensure prompt is provided and not empty
2. **Rate limit exceeded**: Reduce concurrency or add delays between calls
3. **Remote agent not responding**: Check agent URL and network connectivity
4. **Model not found**: Verify model name and provider compatibility

### Debug Tips
- Use `format: "detailed"` to get comprehensive response metadata
- Check Agent Zero logs for detailed error information
- Test remote agents with the agent_bridge tool first
- Verify API keys and provider configurations

## Performance Metrics

Typical performance characteristics:
- **Local GPT-4**: 500-2000ms response time
- **Local GPT-3.5**: 200-800ms response time
- **Remote Agents**: 1000-5000ms (network dependent)
- **Streaming**: 50-200ms time to first token
- **Concurrency**: Up to 10x speedup for batch operations