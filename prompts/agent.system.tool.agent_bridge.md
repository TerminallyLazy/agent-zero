# Agent Bridge Tool

Communicate with remote agents using ACP (Agent Communication Protocol) or A2A (Agent-to-Agent) protocols.

## Tool Name
`agent_bridge`

## Description
The agent bridge tool provides a unified interface for communicating with remote agents that support either ACP or A2A protocols. It automatically detects which protocol a remote agent supports and handles the communication accordingly.

The tool performs protocol auto-detection by:
- **ACP Detection**: Checking for `/.well-known/agent.yml` endpoint
- **A2A Detection**: Attempting a JSON-RPC `getAgentCard` call

## Use Cases
- Discover remote agent capabilities and protocols
- Send messages to remote agents
- Call specific methods on remote agents
- Multi-agent collaboration across different systems
- Protocol-agnostic agent communication

## Arguments

### Required Arguments
- `endpoint` (string): Target agent endpoint URL (with or without http/https prefix)

### Action-Specific Arguments

#### For `action: "discover"` (default)
- `timeout` (number, default: 30): Discovery timeout in seconds

#### For `action: "send"`
- `message` (string): Message to send to the remote agent
- `context` (object, optional): Additional context for A2A messages
- `timeout` (number, default: 30): Request timeout in seconds

#### For `action: "call"`
- `method` (string): Method name to call on the remote agent
- `params` (object/string): Parameters for the method call
- `timeout` (number, default: 30): Request timeout in seconds

## Usage Examples

### Discover Agent Capabilities
```json
{
  "tool_name": "agent_bridge",
  "tool_args": {
    "endpoint": "https://agent.example.com",
    "action": "discover"
  }
}
```

### Send Message to Remote Agent
```json
{
  "tool_name": "agent_bridge",
  "tool_args": {
    "endpoint": "agent.example.com:8080",
    "action": "send",
    "message": "Please analyze the latest market data and provide insights"
  }
}
```

### Call Specific Method (A2A)
```json
{
  "tool_name": "agent_bridge",
  "tool_args": {
    "endpoint": "https://a2a-agent.example.com/rpc",
    "action": "call",
    "method": "generateReport",
    "params": "{\"topic\": \"quarterly_sales\", \"format\": \"pdf\"}"
  }
}
```

### Call REST Endpoint (ACP)
```json
{
  "tool_name": "agent_bridge",
  "tool_args": {
    "endpoint": "https://acp-agent.example.com",
    "action": "call",
    "method": "analyze",
    "params": "{\"data_source\": \"sales_db\", \"timeframe\": \"last_month\"}"
  }
}
```

## Response Formats

### Discovery Response
```json
{
  "protocol": "ACP|A2A|unknown",
  "endpoint": "https://agent.example.com",
  "capabilities": {
    "version": "1.2.0",
    "agent_id": "data-analyzer-01",
    "supported_methods": ["analyze", "report", "status"],
    "description": "Data analysis agent"
  },
  "version": "1.2.0",
  "agent_id": "data-analyzer-01",
  "discovery_url": "https://agent.example.com/.well-known/agent.yml"
}
```

### Message Response
```json
{
  "protocol": "ACP",
  "status": 200,
  "response": {
    "message_id": "msg_123456",
    "status": "received",
    "reply": "I'll analyze the market data and get back to you shortly."
  },
  "message_sent": "Please analyze the latest market data"
}
```

### Method Call Response
```json
{
  "protocol": "A2A",
  "method": "generateReport",
  "status": 200,
  "response": {
    "jsonrpc": "2.0",
    "result": {
      "report_id": "rpt_789012",
      "status": "completed",
      "download_url": "https://agent.example.com/reports/rpt_789012.pdf"
    },
    "id": 1643723400.123
  }
}
```

## Protocol Details

### ACP (Agent Communication Protocol)
- Uses REST-style HTTP endpoints
- Agent info available at `/.well-known/agent.yml`
- Messages sent to `/message` endpoint
- Method calls map to `/{method}` endpoints
- YAML-based configuration format

### A2A (Agent-to-Agent Protocol)
- Uses JSON-RPC 2.0 over HTTP
- Agent info retrieved via `getAgentCard` RPC call
- All communication through RPC endpoints (typically `/rpc` or `/`)
- Supports arbitrary method calls with structured parameters
- JSON-based message format

## Error Handling

The tool provides comprehensive error handling for:

### Discovery Errors
- Network connectivity issues
- Invalid endpoint URLs
- Unsupported protocols
- Malformed agent configurations

### Communication Errors
- Request timeouts
- Protocol-specific errors
- Authentication failures
- Remote agent unavailability

### Example Error Response
```json
{
  "protocol": "unknown",
  "endpoint": "https://invalid-agent.com",
  "error": "No supported protocol detected",
  "attempted": ["ACP", "A2A"]
}
```

## Performance Features

- **Caching**: Agent capabilities are cached to avoid repeated discovery
- **Concurrency Control**: Integrates with Agent Zero's concurrency limiting system
- **Connection Pooling**: Reuses HTTP connections for better performance
- **Timeout Management**: Configurable timeouts prevent hanging requests

## Best Practices

1. **Discovery First**: Always discover agent capabilities before sending messages or calling methods
2. **Error Handling**: Check response status and handle errors gracefully
3. **Timeouts**: Use appropriate timeout values based on expected response times
4. **Caching**: Leverage built-in caching by reusing the same endpoint URLs
5. **Protocol Agnostic**: Don't assume a specific protocol - let the tool detect it automatically

## Security Considerations

- All communications use HTTPS when available
- No automatic credential management - agents should handle their own authentication
- Endpoint validation to prevent invalid URL attacks
- Concurrency limits to prevent resource exhaustion

## Integration Notes

- Compatible with Agent Zero's existing tool system
- Integrates with the concurrency limiting framework
- Supports both synchronous and asynchronous communication patterns
- Can be used with the parallel_executor tool for multi-agent operations

## Troubleshooting

### Common Issues
1. **"No supported protocol detected"**: Check that the remote agent supports ACP or A2A
2. **Connection timeout**: Verify the endpoint URL and network connectivity
3. **Invalid JSON in params**: Ensure method parameters are properly formatted JSON
4. **HTTP 404 errors**: Verify the correct endpoint paths for the agent protocol

### Debug Tips
- Use the discover action first to verify agent availability
- Check Agent Zero logs for detailed error messages
- Verify endpoint URLs include the correct protocol (http/https)
- Test connectivity to the remote agent independently