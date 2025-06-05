# 🎯 Opik Integration Guide for Agent Zero

This guide shows you how to use the newly integrated Opik tracing system with Agent Zero for comprehensive monitoring and observability.

## 🚀 Quick Setup

### 1. Install and Start Opik Locally

**Linux/Mac:**
```bash
git clone https://github.com/comet-ml/opik.git
cd opik
./opik.sh
```

**Windows:**
```powershell
git clone https://github.com/comet-ml/opik.git
cd opik
powershell -ExecutionPolicy ByPass -c ".\opik.ps1"
```

Visit `http://localhost:5173` to access the Opik dashboard.

### 2. Install Opik Python SDK

```bash
pip install opik
opik configure
```

Select local deployment and use `http://localhost:5173` as your server address.

### 3. Configure Agent Zero

Add to your `.env` file:

```bash
# Opik Configuration
OPIK_ENABLED=true
OPIK_USE_LOCAL=true
OPIK_ENDPOINT=http://localhost:5173
OPIK_PROJECT_NAME=agent-zero-traces
OPIK_TRACE_TOOLS=true
OPIK_TRACE_LLM=true
OPIK_TAGS=agent-zero,local-deployment
```

## 📊 What Gets Traced

The Opik integration automatically captures:

### 🤖 LLM Interactions
- Model name and provider
- Input prompts and output responses
- Token usage and duration
- Agent context and metadata

### 🛠️ Tool Executions
- Tool name and arguments
- Execution results and success status
- Duration and error details
- Agent performing the action

### 💬 Agent Conversations
- User messages and agent responses
- Conversation context and metadata
- Success/failure status
- Multi-agent interactions

### 🔄 Custom Workflows
- Multi-step processes
- Nested function calls
- Complex agent orchestrations
- Performance metrics

## 🎯 Usage Examples

### Basic Integration

```python
from python.helpers.opik_init import initialize_opik_integration

# Initialize Opik (call once at startup)
tracker = initialize_opik_integration()

# Your Agent Zero code runs normally
# All LLM calls, tool usage, and conversations are automatically traced
```

### Custom Trace Creation

```python
from python.helpers.opik_client import get_opik_tracker

tracker = get_opik_tracker()

# Start a custom trace
trace_id = tracker.start_trace(
    name="Custom Research Task",
    input_data={"query": "AI trends 2024"},
    metadata={"priority": "high", "department": "research"}
)

# Your code here...

# End the trace
tracker.end_trace(
    trace_id=trace_id,
    output_data={"results": "Research completed"},
    success=True
)
```

### Manual LLM Call Logging

```python
tracker.log_llm_call(
    model_name="gpt-4",
    provider="openai",
    input_text="Explain quantum computing",
    output_text="Quantum computing uses quantum mechanics...",
    tokens_used=150,
    duration=2.5,
    agent_name="Research Agent"
)
```

### Tool Execution Monitoring

```python
tracker.log_tool_execution(
    tool_name="web_search",
    args={"query": "latest news", "max_results": 10},
    result="Found 10 relevant articles",
    success=True,
    duration=1.8,
    agent_name="Search Agent"
)
```

## 📈 Dashboard Features

Access your Opik dashboard at `http://localhost:5173` to view:

### 🔍 Trace Explorer
- Hierarchical view of all traces
- Filter by agent, tool, or time range
- Search through trace content
- Performance analytics

### 📊 Analytics Dashboard
- Token usage statistics
- Tool performance metrics
- Error rate monitoring
- Agent efficiency analysis

### 🎯 Project Management
- Multiple project support
- Team collaboration features
- Custom metadata filtering
- Export capabilities

## 🔧 Advanced Configuration

### Environment Variables

```bash
# Core Settings
OPIK_ENABLED=true                    # Enable/disable tracing
OPIK_PROJECT_NAME=my-project         # Project name in dashboard
OPIK_ENDPOINT=http://localhost:5173  # Opik server URL

# Tracing Options
OPIK_TRACE_TOOLS=true               # Trace tool executions
OPIK_TRACE_LLM=true                 # Trace LLM calls
OPIK_TRACE_SUBORDINATES=true        # Trace sub-agent calls
OPIK_TRACE_ERRORS=true              # Include error traces

# Metadata
OPIK_TAGS=agent-zero,production     # Default tags
OPIK_WORKSPACE=my-workspace         # Workspace name
```

### Programmatic Configuration

```python
from python.helpers.opik_config import OpikConfig
from python.helpers.opik_init import initialize_opik_integration

config = OpikConfig(
    enabled=True,
    project_name="custom-project",
    endpoint="http://localhost:5173",
    trace_tools=True,
    tags=["custom", "experiment"]
)

tracker = initialize_opik_integration(config)
```

## 🎯 Best Practices

### 1. Meaningful Trace Names
```python
# Good
trace_id = tracker.start_trace("User Query: Weather Forecast", ...)

# Better
trace_id = tracker.start_trace("Weather Forecast - NYC - User:123", ...)
```

### 2. Rich Metadata
```python
tracker.start_trace(
    name="Document Analysis",
    input_data={"document": "report.pdf"},
    metadata={
        "user_id": "user123",
        "document_type": "financial_report",
        "priority": "high",
        "department": "finance"
    }
)
```

### 3. Error Handling
```python
try:
    # Your agent code
    result = await agent.process_request(request)
    tracker.end_trace(trace_id, {"result": result}, success=True)
except Exception as e:
    tracker.end_trace(trace_id, {"error": str(e)}, success=False, error=str(e))
```

### 4. Performance Monitoring
```python
import time

start_time = time.time()
# Your code
duration = time.time() - start_time

tracker.log_tool_execution(
    tool_name="data_processor",
    args=args,
    result=result,
    success=True,
    duration=duration,
    agent_name="Data Agent"
)
```

## 🔍 Troubleshooting

### Common Issues

1. **Opik not connecting**: Ensure Opik server is running on `http://localhost:5173`
2. **No traces appearing**: Check `OPIK_ENABLED=true` in environment
3. **Permission errors**: Ensure Opik containers run as non-root users
4. **Performance impact**: Tracing adds minimal overhead (~1-5ms per trace)

### Debug Mode

```python
from python.helpers.opik_init import print_opik_status

# Check current status
print_opik_status()
```

### Flush Traces

```python
# Ensure all traces are sent
tracker = get_opik_tracker()
if tracker:
    tracker.flush()
```

## 🎉 Ready to Go!

Your Agent Zero is now fully integrated with Opik! Every interaction, tool usage, and LLM call will be automatically traced and available in your dashboard at `http://localhost:5173`.

Run the provided examples to see the integration in action:

```bash
python examples/opik_basic_example.py
python examples/opik_advanced_example.py  
python examples/opik_tool_monitoring.py
```

Happy tracing! 🚀
