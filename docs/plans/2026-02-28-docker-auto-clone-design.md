# Context Engine Docker Auto-Clone & Build Design

## Problem

The plugin's `docker-compose.context-engine.yaml` references non-existent images
(`ghcr.io/context-engine-ai/*`). The real Context Engine builds services from
Dockerfiles in its GitHub repository. Users get "denied" errors trying to pull.

## Solution

The Docker handler auto-clones the Context Engine repo, generates a `.env` with
Agent Zero defaults, and runs `docker compose` from the real repo. One toggle in
the settings page handles everything.

## Flow

1. User toggles "Deploy" ON
2. Handler checks if Context Engine repo exists at configured path
3. If missing: `git clone https://github.com/Context-Engine-AI/Context-Engine.git`
4. If `.env` missing: generate from `.env.example` with AZ-specific defaults
5. Run `docker compose up -d` from the cloned repo directory
6. UI shows phase-specific status (cloning → building → running)

## .env Defaults for Agent Zero

```
QDRANT_URL=http://qdrant:6333
COLLECTION_NAME=codebase
EMBEDDING_PROVIDER=remote
EMBEDDING_SERVICE_URL=http://embedding:8100
EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
HOST_INDEX_PATH=<agent-zero-workdir>
CODEBASE_STATE_BACKEND=redis
CODEBASE_STATE_REDIS_URL=redis://redis:6379/0
FASTMCP_HOST=0.0.0.0
FASTMCP_PORT=8000
FASTMCP_INDEXER_PORT=8001
FASTMCP_TRANSPORT=sse
FASTMCP_HTTP_TRANSPORT=streamable-http
FASTMCP_HTTP_PORT=8002
FASTMCP_INDEXER_HTTP_PORT=8003
```

## Files Changed

| File | Action |
|------|--------|
| `api/docker.py` | Rewrite: add clone, .env generation, real repo compose |
| `webui/config.html` | Modify: add repo_path field, cloning/building states |
| `default_config.yaml` | Modify: add context_engine_repo_path |
| `docker-compose.context-engine.yaml` | Delete: no longer needed |
