# Context Engine Docker Services UI

## Problem

The Context Engine plugin requires 7 Docker services (Qdrant, Redis, Embedding, 4 MCP endpoints) running via `docker-compose.context-engine.yaml`. Users currently must run `docker compose` commands manually from the terminal. There is no way to deploy, stop, or verify these services from within Agent Zero's UI.

## Decision

Add a Docker Services section to the plugin settings page (`config.html`) with a deploy/stop toggle and a test connection button, backed by a new API handler (`api/docker.py`).

## Design

### Backend: `api/docker.py`

A `DockerHandler` class following the existing `StatusHandler`/`SearchHandler` pattern.

**Actions:**

| Action | Command | Timeout | Returns |
|--------|---------|---------|---------|
| `up` | `docker compose -f <path> up -d` | 120s | `{ok, output}` or `{ok: false, error, output}` |
| `down` | `docker compose -f <path> down` | 30s | `{ok, output}` or `{ok: false, error, output}` |
| `ps` | `docker compose -f <path> ps --format json` | 30s | `{ok, running, services, service_count}` |

**Compose file resolution:** `Path(__file__).parent.parent / "docker-compose.context-engine.yaml"`

**Error handling:**
- Docker not installed: catches `FileNotFoundError`, returns friendly message
- Compose file missing: checks `path.exists()` before running
- Process timeout: kills subprocess, returns error with suggestion to pull manually
- Non-zero exit: captures stderr, returns in error field

### Frontend: `webui/config.html`

New "Docker Services" section at the top of the settings page, before endpoint fields.

**Components:**
1. Toggle switch (Deploy Services) - calls `up` or `down`
2. Status indicator - shows Running/Stopped/Starting/Stopping/Error with service count
3. Test Connection button - calls existing `/plugins/context-engine/status` endpoint
4. Connection result - shows green check or red X with error message

**Alpine.js state:**
```js
{
  dockerStatus: 'unknown',  // running | stopped | starting | stopping | error
  dockerError: '',
  dockerServiceCount: 0,
  connectionOk: null,       // null | true | false
  connectionError: '',
  testingConnection: false
}
```

**Behavior:**
- On page load: call `ps` to determine current state, set toggle accordingly
- Toggle ON: call `up`, show "Starting..." spinner, disable toggle during operation
- Toggle OFF: call `down`, show "Stopping..." spinner
- Test Connection: call `/status`, show result

### Files

| File | Action | Purpose |
|------|--------|---------|
| `api/docker.py` | Create | DockerHandler with up/down/ps actions |
| `webui/config.html` | Modify | Add Docker Services section at top |

### Assumptions

- Docker images at `ghcr.io/context-engine-ai/*` are publicly accessible (no registry auth needed)
- Docker and Docker Compose are installed on the host
- The compose file lives in the plugin root directory

### Test Plan

1. Containers stopped: UI shows "Stopped", toggle OFF
2. Toggle ON: "Starting..." then "Running (7/7)"
3. Test Connection: green check when MCP endpoints respond
4. Toggle OFF: "Stopping..." then "Stopped"
5. Docker not installed: friendly error message
6. Partial startup: accurate service count in warning state
