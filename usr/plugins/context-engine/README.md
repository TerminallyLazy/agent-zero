# Context Engine Plugin for Agent Zero

Semantic code search, symbol graph queries, context-aware Q&A, and persistent
developer memory — powered by [Context Engine](https://github.com/Context-Engine-AI/Context-Engine)
MCP services.

## What It Does

This plugin gives every Agent Zero agent access to eight specialized tools:

| Tool | Description |
|------|-------------|
| `code_search` | Hybrid semantic + lexical search across your codebase |
| `context_answer` | Ask natural-language questions answered with code context |
| `symbol_graph` | Query callers, callees, and relationships for any symbol |
| `context_index` | Trigger indexing of files or directories on demand |
| `ce_memory_store` | Store knowledge (decisions, patterns, learnings) |
| `ce_memory_find` | Retrieve stored memories by semantic similarity |
| `search_tests` | Find test files related to a query |
| `search_callers` | Find callers of a function or symbol |

When **auto-context** is enabled, the plugin automatically injects relevant code
snippets into the agent's context during conversations — the agent gets codebase
awareness without explicit tool calls.

## Prerequisites

- Agent Zero running (locally or in Docker)
- Docker and Docker Compose (for the containerized Context Engine services)
- At least 8 GB free RAM (Qdrant + embedding models + MCP services)

## Installation

### 1. Enable the plugin

The plugin lives at `usr/plugins/context-engine/`. Agent Zero discovers it
automatically via `plugin.yaml`. Toggle it on from the Agent Zero settings UI
or by creating the activation marker:

```
touch usr/plugins/context-engine/.toggle-1
```

### 2. Start Context Engine services

```bash
cd usr/plugins/context-engine
docker compose -f docker-compose.context-engine.yaml up -d
```

This starts seven services:

| Service | Port | Purpose |
|---------|------|---------|
| `ce-qdrant` | 6333, 6334 | Vector database (storage) |
| `ce-redis` | 6379 | Cache and state backend |
| `ce-embedding` | 8100 | ONNX embedding model (2 replicas) |
| `ce-mcp` | 8000 | MCP search server (SSE transport) |
| `ce-mcp-http` | 8002 | MCP search server (HTTP/JSON-RPC) |
| `ce-mcp-indexer` | 8001 | MCP indexer server (SSE transport) |
| `ce-mcp-indexer-http` | 8003 | MCP indexer server (HTTP/JSON-RPC) |

### 3. Index your codebase

Use Agent Zero to trigger indexing, or call the indexer directly:

```
Agent, please index the current project using context_index.
```

## Configuration

Open the Agent Zero settings UI and navigate to the **Context Engine** section,
or edit `usr/plugins/context-engine/default_config.yaml` directly:

```yaml
indexer_endpoint: http://localhost:8003   # MCP indexer (HTTP)
memory_endpoint: http://localhost:8002    # MCP search/memory (HTTP)
collection_name: codebase                # Qdrant collection name
search_limit: 10                         # Default result count
search_threshold: 0.7                    # Minimum similarity score
auto_context_enabled: true               # Inject context automatically
auto_context_interval: 3                 # Every N messages
auto_context_max_results: 5              # Snippets per injection
auto_context_history_len: 10000          # Chars of history to analyze
connection_timeout: 10                   # HTTP timeout in seconds
```

### Docker Compose environment variables

The `docker-compose.context-engine.yaml` file accepts these overrides:

| Variable | Default | Description |
|----------|---------|-------------|
| `CE_WORKDIR` | `./workdir` | Host path to mount as `/work` (your codebase) |
| `CE_COLLECTION` | `codebase` | Qdrant collection name |
| `CE_EMBEDDING_MODEL` | `nomic-ai/nomic-embed-text-v1.5` | HuggingFace embedding model |
| `CE_EMBEDDING_PROVIDER` | `remote` | `remote` (embedding service) or `local` |
| `CE_EMBEDDING_REPLICAS` | `2` | Number of embedding service replicas |

Example — index a specific project directory:

```bash
CE_WORKDIR=/path/to/your/project docker compose -f docker-compose.context-engine.yaml up -d
```

## Usage Examples

Once services are running and a codebase is indexed, agents can use the tools
naturally in conversation:

**Code search:**
> "Find all functions that handle authentication"

The agent calls `code_search` with the query and returns ranked results with
file paths and code snippets.

**Context-aware Q&A:**
> "How does the WebSocket connection get established in this project?"

The agent calls `context_answer`, which searches the codebase and synthesizes
an answer grounded in actual code.

**Symbol relationships:**
> "Who calls the `process_message` function?"

The agent calls `symbol_graph` with `query_type=callers` to trace call
relationships through the AST-derived graph.

**Memory:**
> "Remember that we decided to use aiohttp instead of httpx for all HTTP clients"

The agent calls `ce_memory_store`. Later, when relevant context arises, the
agent (or auto-context) retrieves it via `ce_memory_find`.

## Architecture

```
Agent Zero (port 50001)
  |
  |-- Context Engine Plugin
  |     |-- tools/          8 Tool subclasses
  |     |-- helpers/        ContextEngineClient (aiohttp)
  |     |-- extensions/     Auto-context injection
  |     |-- api/            WebUI API handlers
  |     `-- webui/          Dashboard + settings UI
  |
  `-- HTTP (JSON-RPC) --+
                        |
        +---------------+---------------+
        |                               |
  MCP Search (8002)            MCP Indexer (8003)
        |                               |
        +-------+-------+       +-------+-------+
                |               |               |
           Qdrant (6333)   Redis (6379)   Embedding (8100)
```

The plugin communicates with Context Engine via HTTP/JSON-RPC (ports 8002 and
8003). The MCP servers handle search, indexing, and memory operations backed by
Qdrant vector storage, Redis state management, and ONNX-based embeddings.

## Troubleshooting

### Services won't start

Check Docker is running and ports are free:

```bash
docker compose -f docker-compose.context-engine.yaml ps
docker compose -f docker-compose.context-engine.yaml logs ce-qdrant
```

### "Connection error" in Agent Zero

Verify the endpoints match your Docker setup:

```bash
# Should return a JSON response
curl -s http://localhost:8003 | head -c 200
```

If running Agent Zero in Docker, use the Docker network hostname instead of
`localhost` — set the endpoints to `http://ce-mcp-http:8000` and
`http://ce-mcp-indexer-http:8001` in the plugin settings.

### Embedding service takes long to start

The first startup downloads the embedding model (~500 MB). Subsequent starts
use the cached model from the `ce_embedding_cache` volume. Check progress:

```bash
docker compose -f docker-compose.context-engine.yaml logs -f ce-embedding
```

### Reset everything

```bash
docker compose -f docker-compose.context-engine.yaml down -v
```

This removes all containers and volumes (including indexed data).

## Further Reading

- [Agent Zero Plugin Guide](../../AGENTS.plugins.md) — how Agent Zero plugins work
- [Context Engine GitHub](https://github.com/Context-Engine-AI/Context-Engine) — upstream project
