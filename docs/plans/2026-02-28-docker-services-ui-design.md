# Context Engine Docker Services UI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Docker deploy toggle and test connection button to the Context Engine plugin settings UI.

**Architecture:** A new `api/docker.py` handler runs `docker compose` commands via `asyncio.create_subprocess_exec`. The existing `webui/config.html` gets a new "Docker Services" section at the top with an Alpine.js-driven toggle, status indicator, and test connection button. No new config fields — Docker state is derived at runtime.

**Tech Stack:** Python 3 (asyncio subprocess), Alpine.js, Agent Zero plugin API framework (Flask-based `ApiHandler`).

---

### Task 1: Create the Docker API handler

**Files:**
- Create: `usr/plugins/context-engine/api/docker.py`

**Step 1: Write the handler**

Create `usr/plugins/context-engine/api/docker.py`:

```python
import asyncio
import json

from python.helpers.api import ApiHandler, Request, Response

from pathlib import Path

_plugin_root = Path(__file__).parent.parent
_compose_file = _plugin_root / "docker-compose.context-engine.yaml"


class DockerHandler(ApiHandler):
    """Deploy, stop, and check status of Context Engine Docker services."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = input.get("action", "").strip().lower()
        if action not in ("up", "down", "ps"):
            return {"ok": False, "error": "Invalid action. Use 'up', 'down', or 'ps'."}

        if not _compose_file.is_file():
            return {"ok": False, "error": f"Compose file not found: {_compose_file.name}"}

        try:
            if action == "up":
                return await self._run_compose(["up", "-d"], timeout=120)
            elif action == "down":
                return await self._run_compose(["down"], timeout=30)
            else:  # ps
                return await self._get_status()
        except FileNotFoundError:
            return {"ok": False, "error": "Docker is not installed or not in PATH."}
        except asyncio.TimeoutError:
            return {"ok": False, "error": "Operation timed out. Try running 'docker compose pull' manually first."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _run_compose(self, args: list[str], timeout: int) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", str(_compose_file), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = (stdout.decode() + stderr.decode()).strip()
        if proc.returncode == 0:
            return {"ok": True, "output": output}
        return {"ok": False, "error": output or f"docker compose {args[0]} failed", "output": output}

    async def _get_status(self) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", str(_compose_file), "ps", "--format", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            return {"ok": False, "running": False, "error": stderr.decode().strip(), "services": []}

        raw = stdout.decode().strip()
        if not raw:
            return {"ok": True, "running": False, "services": [], "service_count": 0}

        # docker compose ps --format json outputs one JSON object per line
        services = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                svc = json.loads(line)
                services.append({
                    "name": svc.get("Name", svc.get("Service", "")),
                    "state": svc.get("State", ""),
                    "status": svc.get("Status", ""),
                })
            except json.JSONDecodeError:
                continue

        running_count = sum(1 for s in services if s["state"] == "running")
        return {
            "ok": True,
            "running": running_count > 0 and running_count == len(services),
            "services": services,
            "service_count": len(services),
            "running_count": running_count,
        }
```

**Step 2: Verify the handler loads**

Run: `cd /Users/lazy/intent/workspaces/full-create/agent-zero && python -c "from pathlib import Path; print(Path('usr/plugins/context-engine/api/docker.py').is_file())"`
Expected: `True`

**Step 3: Commit**

```bash
git add usr/plugins/context-engine/api/docker.py
git commit -m "feat(context-engine): add Docker compose API handler"
```

---

### Task 2: Add Docker Services section to settings UI

**Files:**
- Modify: `usr/plugins/context-engine/webui/config.html`

**Step 1: Add the Docker Services section**

Insert a new section at the top of `config.html`, right after the opening `<div>` inside the `<template x-if>`, before the existing "Context Engine" section-title. The section uses inline Alpine.js `x-data` with `x-init` to check Docker status on load.

Replace the beginning of config.html (lines 1-14) with:

```html
<html>
<head>
    <title>Context Engine</title>
    <style>
        .docker-section {
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--color-border, #333);
        }
        .docker-status {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-top: 0.5rem;
            font-size: 0.9rem;
        }
        .docker-status .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }
        .dot-green { background: #4caf50; }
        .dot-orange { background: #ff9800; }
        .dot-red { background: #f44336; }
        .dot-gray { background: #666; }
        .docker-btn {
            margin-top: 0.75rem;
            padding: 0.4rem 1rem;
            border: 1px solid var(--color-border, #555);
            border-radius: 4px;
            background: var(--color-panel, #1e1e1e);
            color: var(--color-text, #ccc);
            cursor: pointer;
            font-size: 0.85rem;
        }
        .docker-btn:hover { opacity: 0.85; }
        .docker-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .docker-conn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-top: 0.5rem;
            font-size: 0.85rem;
        }
    </style>
</head>

<body>
    <div x-data="{
        dockerStatus: 'unknown',
        dockerError: '',
        dockerServiceCount: 0,
        dockerRunningCount: 0,
        dockerBusy: false,
        connectionOk: null,
        connectionError: '',
        testingConnection: false,

        async init() {
            await this.checkDockerStatus();
        },

        async apiCall(endpoint, data) {
            const res = await fetch('/api/plugins/context-engine/' + endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': document.cookie.match(/csrf_token_[^=]+=([^;]+)/)?.[1] || ''
                },
                credentials: 'same-origin',
                body: JSON.stringify(data)
            });
            return await res.json();
        },

        async checkDockerStatus() {
            try {
                const result = await this.apiCall('docker', { action: 'ps' });
                if (result.ok) {
                    this.dockerServiceCount = result.service_count || 0;
                    this.dockerRunningCount = result.running_count || 0;
                    this.dockerStatus = result.running ? 'running' : (this.dockerServiceCount > 0 ? 'partial' : 'stopped');
                    this.dockerError = '';
                } else {
                    this.dockerStatus = 'error';
                    this.dockerError = result.error || 'Unknown error';
                }
            } catch (e) {
                this.dockerStatus = 'error';
                this.dockerError = e.message || 'Failed to check status';
            }
        },

        get dockerToggled() {
            return this.dockerStatus === 'running' || this.dockerStatus === 'partial' || this.dockerStatus === 'starting';
        },

        async toggleDocker() {
            if (this.dockerBusy) return;
            this.dockerBusy = true;
            this.dockerError = '';

            const wantUp = this.dockerStatus === 'stopped' || this.dockerStatus === 'error' || this.dockerStatus === 'unknown';
            this.dockerStatus = wantUp ? 'starting' : 'stopping';

            try {
                const result = await this.apiCall('docker', { action: wantUp ? 'up' : 'down' });
                if (result.ok) {
                    await this.checkDockerStatus();
                } else {
                    this.dockerStatus = 'error';
                    this.dockerError = result.error || 'Operation failed';
                }
            } catch (e) {
                this.dockerStatus = 'error';
                this.dockerError = e.message || 'Operation failed';
            } finally {
                this.dockerBusy = false;
            }
        },

        async testConnection() {
            this.testingConnection = true;
            this.connectionOk = null;
            this.connectionError = '';
            try {
                const result = await this.apiCall('status', {});
                this.connectionOk = result.ok && result.connected;
                if (!this.connectionOk) {
                    this.connectionError = result.error || 'MCP endpoints not responding';
                }
            } catch (e) {
                this.connectionOk = false;
                this.connectionError = e.message || 'Connection test failed';
            } finally {
                this.testingConnection = false;
            }
        }
    }">
        <template x-if="$store.pluginSettings.settings">
            <div>
                <!-- Docker Services Section -->
                <div class="docker-section">
                    <div class="section-title">Docker Services</div>
                    <div class="section-description">
                        Deploy and manage the Context Engine Docker stack (Qdrant, Redis, Embedding, MCP services).
                    </div>

                    <div class="field">
                        <div class="field-label">
                            <div class="field-title">Deploy Services</div>
                            <div class="field-description">
                                Start or stop all Context Engine Docker containers.
                            </div>
                        </div>
                        <div class="field-control">
                            <label class="toggle">
                                <input type="checkbox"
                                    :checked="dockerToggled"
                                    @change="toggleDocker()"
                                    :disabled="dockerBusy" />
                                <span class="toggler"></span>
                            </label>
                        </div>
                    </div>

                    <div class="docker-status">
                        <template x-if="dockerStatus === 'running'">
                            <span><span class="dot dot-green"></span> Running (<span x-text="dockerRunningCount"></span>/<span x-text="dockerServiceCount"></span> services)</span>
                        </template>
                        <template x-if="dockerStatus === 'partial'">
                            <span><span class="dot dot-orange"></span> Partial (<span x-text="dockerRunningCount"></span>/<span x-text="dockerServiceCount"></span> services running)</span>
                        </template>
                        <template x-if="dockerStatus === 'stopped'">
                            <span><span class="dot dot-gray"></span> Stopped</span>
                        </template>
                        <template x-if="dockerStatus === 'starting'">
                            <span><span class="dot dot-orange"></span> Starting&hellip;</span>
                        </template>
                        <template x-if="dockerStatus === 'stopping'">
                            <span><span class="dot dot-orange"></span> Stopping&hellip;</span>
                        </template>
                        <template x-if="dockerStatus === 'error'">
                            <span><span class="dot dot-red"></span> Error: <span x-text="dockerError"></span></span>
                        </template>
                        <template x-if="dockerStatus === 'unknown'">
                            <span><span class="dot dot-gray"></span> Checking&hellip;</span>
                        </template>
                    </div>

                    <button class="docker-btn" @click="testConnection()" :disabled="testingConnection">
                        <span x-text="testingConnection ? 'Testing...' : 'Test Connection'"></span>
                    </button>

                    <template x-if="connectionOk === true">
                        <div class="docker-conn">
                            <span style="color: #4caf50;">&#10003;</span> MCP endpoints responding
                        </div>
                    </template>
                    <template x-if="connectionOk === false">
                        <div class="docker-conn">
                            <span style="color: #f44336;">&#10007;</span> <span x-text="connectionError"></span>
                        </div>
                    </template>
                </div>

                <!-- Original Settings Section -->
                <div class="section-title">Context Engine</div>
                <div class="section-description">
                    Integration with Context Engine for semantic code search, symbol graph queries, context-aware Q&A,
                    and persistent developer memory.
                </div>
```

The rest of `config.html` (lines 16-160, from the first `<div class="field">` for Indexer Endpoint onwards) stays unchanged.

**Step 2: Verify the HTML is valid**

Open Agent Zero settings UI in the browser. Navigate to the Context Engine plugin settings. Verify:
- The Docker Services section appears at the top
- The toggle reflects actual container state
- The existing settings fields appear below

**Step 3: Commit**

```bash
git add usr/plugins/context-engine/webui/config.html
git commit -m "feat(context-engine): add Docker deploy toggle and test connection to settings"
```

---

### Task 3: Manual integration test

**Step 1: Test with containers stopped**

1. Ensure all context-engine containers are stopped: `docker compose -f usr/plugins/context-engine/docker-compose.context-engine.yaml down`
2. Open Agent Zero settings → Context Engine
3. Verify: toggle is OFF, status shows "Stopped"

**Step 2: Test deploy**

1. Toggle ON
2. Verify: status shows "Starting..."
3. Wait for completion
4. Verify: status shows "Running (7/7 services)" or appropriate count

**Step 3: Test connection**

1. Click "Test Connection"
2. Verify: green check "MCP endpoints responding" (or red X if services aren't ready yet)

**Step 4: Test stop**

1. Toggle OFF
2. Verify: status shows "Stopping..." then "Stopped"

**Step 5: Commit final state**

```bash
git add -A usr/plugins/context-engine/
git commit -m "feat(context-engine): Docker services UI integration complete"
```
