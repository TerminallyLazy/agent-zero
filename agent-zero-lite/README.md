# Agent Zero Lite

A lightweight, cross-platform implementation of Agent Zero that maintains core functionality while reducing complexity and dependencies.

## Features

✅ **Full LiteLLM Support** - 100+ AI providers (OpenAI, Anthropic, Google, local models, etc.)  
✅ **Web UI** - Complete interface at localhost:50001  
✅ **Vector Memory** - FAISS-based persistent memory  
✅ **Document RAG** - PDF, text, and document processing  
✅ **Multi-Agent** - Superior/subordinate agent hierarchy  
✅ **MCP Client** - Model Context Protocol integration  
✅ **Local Execution** - Python, Node.js, and terminal  
✅ **Tunneling** - Remote access support  
✅ **File Management** - Work directory browser  

## Removed from Full Version

❌ Browser automation (Playwright)  
❌ Docker/SSH execution  
❌ Speech processing (STT/TTS)  
❌ Task scheduling  
❌ Backup/restore system  
❌ Web search tools  

## Quick Start

1. Install (CPU-only by default):
```bash
pip install agent-zero-lite
```

- Optional extras:
  - CPU ML helpers (additional ONNX/Transformers utilities):
    ```bash
    pip install "agent-zero-lite[cpu]"
    ```
  - Transformers stack (CPU) and ONNX runtime (sentence-transformers included by default):
    ```bash
    pip install "agent-zero-lite[ml]"
    ```
  - Audio transcription (Whisper, CPU):
    ```bash
    pip install "agent-zero-lite[audio]"
    ```
  - GPU stack (advanced; choose your CUDA build of torch separately if needed):
    ```bash
    pip install "agent-zero-lite[gpu]"
    # For PyTorch CUDA builds, see: https://pytorch.org/get-started/locally/
    ```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. Start the Web UI:
```bash
python run_ui.py
```

4. **Open browser:**
   ```
   http://localhost:50001
   ```

## Configuration

### Minimal Setup
Set at least one LLM provider in `.env`:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Or Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Or local Ollama
CHAT_MODEL_PROVIDER=ollama
CHAT_MODEL_NAME=llama3.1:8b
OLLAMA_API_BASE=http://localhost:11434
```

### Full Configuration
See `.env.example` for all available options including:
- All 100+ LiteLLM providers
- Model configurations  
- Rate limiting settings
- MCP server integration
- Memory and knowledge settings

## Supported Models

Agent Zero Lite supports **all LiteLLM providers**:

### Commercial APIs
- **OpenAI:** GPT-4o, GPT-4, GPT-3.5, etc.
- **Anthropic:** Claude 3.5 Sonnet, Claude 3 Opus, etc.
- **Google:** Gemini 1.5 Pro, Gemini 1.5 Flash, etc.
- **Groq:** Llama 3.1, Mixtral, etc. (fast inference)
- **Together AI:** Llama, Mistral, etc.
- **Mistral AI:** Mistral Large, Mistral 7B, etc.
- **Cohere:** Command R+, Command Light, etc.

### Local Models
- **Ollama:** Any local model (llama3.1, mistral, etc.)
- **LM Studio:** Local model server
- **Text Generation WebUI:** Local inference
- **VLLM:** High-performance inference server

### Enterprise
- **Azure OpenAI:** Enterprise GPT models
- **AWS Bedrock:** Claude, Titan, etc.
- **Google Vertex AI:** Enterprise Gemini
- **Hugging Face:** Hosted models

## Usage Examples

### Basic Chat
```python
from agent import AgentContext
import initialize

# Initialize agent
config = initialize.initialize_agent()
context = AgentContext(config)

# Send message
response = context.communicate("Hello, what can you help me with?")
```

### Code Execution
The agent can execute Python, Node.js, and terminal commands:

```
User: "Create a Python script that calculates fibonacci numbers"
Agent: Uses code_execution tool to write and run Python code
```

### Document Processing
```
User: "Analyze this PDF document and summarize the key points"
Agent: Uses document_query tool to process and analyze documents
```

### Multi-Agent Collaboration
```
User: "Create a complex analysis using multiple specialized agents"
Agent: Uses call_subordinate to delegate tasks to specialized sub-agents
```

## Architecture

Agent Zero Lite maintains the core Agent Zero architecture:

- **Agent Loop:** Reason → Tool Use → Response cycle
- **Tool System:** Extensible plugin architecture  
- **Memory:** FAISS vector database for persistent memory
- **Extensions:** Hook-based system for customization
- **Prompts:** Template-based prompt management

## Development

### Adding Tools
Create new tools in `python/tools/`:

```python
from python.helpers.tool import Tool, Response

class MyTool(Tool):
    async def execute(self, **kwargs):
        # Tool logic here
        return Response(message="result", break_loop=False)
```

### Adding Extensions
Create extensions in `python/extensions/`:

```python
from python.helpers.extension import Extension

class MyExtension(Extension):
    async def execute(self, **kwargs):
        # Extension logic here
        pass
```

## Troubleshooting

### Common Issues

1. **Model not responding:** Check API keys in `.env`
2. **Port in use:** Change PORT in `.env` 
3. **Memory issues:** Reduce context length settings
4. **Missing dependencies:** Run `pip install -r requirements.txt`

### Debugging

Enable debug logging by setting:
```bash
LITELLM_LOG=DEBUG
```

## Migration

### From Full Agent Zero
1. Copy `.env` settings
2. Copy `memory/` and `knowledge/` folders  
3. Copy `work_dir/` contents
4. Remove Docker/SSH configurations

### To Full Agent Zero  
1. Install additional dependencies
2. Add Docker/SSH configurations
3. No data migration needed

## Performance

Agent Zero Lite is optimized for:
- **Startup:** ~3 seconds vs 15+ seconds
- **Memory:** ~200MB vs 1GB+ RAM usage  
- **Dependencies:** ~30 packages vs 45+ packages
- **Installation:** <2 minutes vs 10+ minutes

## License

Same as Agent Zero - check the original repository for license terms.

## Support

For issues and questions:
1. Check this README
2. Review `.env.example` configuration
3. See the original Agent Zero documentation
4. Report issues to the Agent Zero repository