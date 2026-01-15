# Phase 4: Docker Sidecar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Docker sidecar execution mode for LitePali, providing maximum isolation and consistent deployment in containerized environments.

**Architecture:** Create a standalone Docker container running the visual document worker, communicating via HTTP instead of stdin/stdout. The container mounts shared volumes for index storage and is managed via Agent Zero's DockerContainerManager.

**Tech Stack:** Docker, FastAPI (lightweight HTTP server), Agent Zero's DockerContainerManager, existing visual_document_worker.py as base.

---

## Task 1: Create HTTP Server Wrapper for Worker

**Files:**
- Create: `python/helpers/visual_document_http_server.py`
- Test: Manual testing via curl

**Step 1: Write the HTTP server**

Create a FastAPI-based HTTP server that wraps the existing worker logic:

```python
#!/usr/bin/env python3
"""
HTTP server wrapper for visual document worker.
Used by Docker sidecar mode.

Endpoints:
    POST /index - Index a document
    POST /search - Search indexed documents
    GET /status - Get worker status
    GET /health - Health check endpoint
    POST /shutdown - Graceful shutdown
"""

import asyncio
import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn


# Request/Response models
class IndexRequest(BaseModel):
    uri: str
    pdf_path: str
    output_dir: str
    settings: Dict[str, Any] = {}


class SearchRequest(BaseModel):
    query: str
    document_uris: Optional[List[str]] = None
    limit: int = 5
    settings: Dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    indexed_documents: int


class APIResponse(BaseModel):
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None


app = FastAPI(title="Visual Document Service", version="1.0.0")

# Worker state (module-level singleton)
_litepali = None
_model_name: Optional[str] = None
_indexed_docs: Dict[str, dict] = {}


def _log(message: str) -> None:
    """Log to stderr."""
    print(f"[http-server] {message}", file=sys.stderr, flush=True)


def _ensure_litepali(model_name: str = "vidore/colpali-v1.2") -> None:
    """Initialize LitePali if needed."""
    global _litepali, _model_name

    if _litepali is not None and _model_name == model_name:
        return

    _log(f"Loading LitePali model: {model_name}")

    try:
        from litepali import LitePali
    except ImportError as e:
        raise ImportError(
            "LitePali not installed. Run: pip install litepali colpali-engine"
        ) from e

    import torch
    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

    _litepali = LitePali(model_name=model_name, device=device)
    _model_name = model_name
    _log(f"LitePali loaded on {device}")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Docker."""
    return HealthResponse(
        status="healthy",
        model_loaded=_litepali is not None,
        indexed_documents=len(_indexed_docs)
    )


@app.get("/status", response_model=APIResponse)
async def get_status():
    """Get detailed worker status."""
    return APIResponse(
        success=True,
        result={
            "model_loaded": _litepali is not None,
            "model_name": _model_name,
            "indexed_documents": len(_indexed_docs),
            "documents": list(_indexed_docs.keys())
        }
    )


@app.post("/index", response_model=APIResponse)
async def index_document(request: IndexRequest):
    """Index a document."""
    try:
        from litepali import ImageFile
        import pdf2image

        settings = request.settings
        model_name = settings.get("model_name", "vidore/colpali-v1.2")
        dpi = settings.get("pdf_dpi", 144)
        max_pages = settings.get("max_pages", 50)
        batch_size = settings.get("batch_size", 4)

        _ensure_litepali(model_name)

        output_dir = Path(request.output_dir)
        images_dir = output_dir / "images"
        os.makedirs(images_dir, exist_ok=True)

        _log(f"Converting PDF to images: {request.pdf_path}")
        images = pdf2image.convert_from_path(
            request.pdf_path,
            dpi=dpi,
            first_page=1,
            last_page=max_pages
        )

        image_paths = []
        for i, image in enumerate(images):
            image_path = images_dir / f"page_{i+1:03d}.png"
            image.save(image_path, "PNG")
            image_paths.append(str(image_path))

        _log(f"Converted {len(image_paths)} pages")

        doc_hash = hashlib.sha256(request.uri.encode()).hexdigest()[:12]

        _log("Processing images through vision model...")
        for i, img_path in enumerate(image_paths):
            _litepali.add(ImageFile(
                path=img_path,
                document_id=doc_hash,
                page_id=str(i + 1),
                metadata={"uri": request.uri, "page": i + 1}
            ))

        _litepali.process(batch_size=batch_size)

        _indexed_docs[doc_hash] = {
            "uri": request.uri,
            "page_count": len(image_paths),
            "image_paths": image_paths
        }

        return APIResponse(
            success=True,
            result={
                "doc_hash": doc_hash,
                "page_count": len(image_paths),
                "image_paths": image_paths
            }
        )

    except Exception as e:
        _log(f"Error indexing: {e}")
        return APIResponse(success=False, error=str(e))


@app.post("/search", response_model=APIResponse)
async def search_documents(request: SearchRequest):
    """Search indexed documents."""
    try:
        settings = request.settings
        model_name = settings.get("model_name", "vidore/colpali-v1.2")
        _ensure_litepali(model_name)

        doc_hashes = None
        if request.document_uris:
            doc_hashes = [
                hashlib.sha256(uri.encode()).hexdigest()[:12]
                for uri in request.document_uris
            ]

        results = _litepali.search(request.query, k=request.limit * 2)

        matches = []
        for result in results:
            if doc_hashes and result.document_id not in doc_hashes:
                continue

            matches.append({
                "document_uri": result.metadata.get("uri", ""),
                "page_number": int(result.metadata.get("page", 0)),
                "score": float(result.score),
                "image_path": result.path
            })

            if len(matches) >= request.limit:
                break

        return APIResponse(success=True, result=matches)

    except Exception as e:
        _log(f"Error searching: {e}")
        return APIResponse(success=False, error=str(e))


@app.post("/shutdown")
async def shutdown():
    """Graceful shutdown."""
    _log("Shutdown requested")
    # Schedule shutdown after response
    asyncio.get_event_loop().call_later(0.5, lambda: os._exit(0))
    return APIResponse(success=True, result="shutting down")


def main():
    """Entry point."""
    port = int(os.environ.get("PORT", "9010"))
    host = os.environ.get("HOST", "0.0.0.0")
    _log(f"Starting HTTP server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
```

**Step 2: Verify the file exists**

Run: `ls -la python/helpers/visual_document_http_server.py`
Expected: File exists with ~200 lines

**Step 3: Commit**

```bash
git add python/helpers/visual_document_http_server.py
git commit -m "feat: add HTTP server wrapper for visual document worker"
```

---

## Task 2: Create Dockerfile for Visual Document Service

**Files:**
- Create: `docker/visual_document_service/Dockerfile`
- Create: `docker/visual_document_service/requirements.txt`

**Step 1: Create requirements.txt**

```txt
# Visual document service dependencies
litepali>=0.0.5
colpali-engine>=0.3.0,<0.4.0
safetensors>=0.4.0
pdf2image>=1.16.0
torch>=2.0.0
fastapi>=0.100.0
uvicorn>=0.23.0
pydantic>=2.0.0
```

**Step 2: Create Dockerfile**

```dockerfile
# Visual Document Service - LitePali sidecar container
FROM python:3.11-slim

# Install system dependencies for pdf2image
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the HTTP server module
COPY ../../python/helpers/visual_document_http_server.py /app/server.py

# Create directories for shared volumes
RUN mkdir -p /a0/usr/visual_docs

# Environment configuration
ENV PORT=9010
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:9010/health || exit 1

# Expose the service port
EXPOSE 9010

# Run the HTTP server
CMD ["python", "server.py"]
```

**Step 3: Verify files exist**

Run: `ls -la docker/visual_document_service/`
Expected: Dockerfile and requirements.txt exist

**Step 4: Commit**

```bash
git add docker/visual_document_service/
git commit -m "feat: add Dockerfile for visual document sidecar service"
```

---

## Task 3: Create Docker Sidecar Service Client

**Files:**
- Create: `python/helpers/visual_document_docker_service.py`
- Test: Unit test for client methods (mocked)

**Step 1: Write the Docker sidecar service client**

```python
"""
Docker sidecar service client for visual document processing.

Manages a Docker container running the visual document HTTP service.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

import aiohttp

from python.helpers.docker import DockerContainerManager
from python.helpers.files import get_abs_path
from python.helpers.print_style import PrintStyle


class VisualDocumentDockerService:
    """
    Manages LitePali in a Docker sidecar container.

    Communicates via HTTP to the containerized service.
    """

    _instance: Optional["VisualDocumentDockerService"] = None

    # Docker configuration
    IMAGE_NAME = "agent0ai/visual-document-service:latest"
    CONTAINER_NAME = "a0-visual-document-service"
    SERVICE_PORT = 9010
    HEALTH_CHECK_TIMEOUT = 60  # seconds

    def __init__(self):
        self._docker_manager: Optional[DockerContainerManager] = None
        self._started = False
        self._base_url: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None

    @classmethod
    def get_instance(cls) -> "VisualDocumentDockerService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_volume_mounts(self) -> Dict[str, Dict[str, str]]:
        """Get volume mounts for shared storage."""
        # Mount the global visual docs directory
        visual_docs_path = get_abs_path("usr/visual_docs")
        os.makedirs(visual_docs_path, exist_ok=True)

        return {
            visual_docs_path: {"bind": "/a0/usr/visual_docs", "mode": "rw"}
        }

    async def start(self) -> bool:
        """
        Start the Docker sidecar container.

        Returns:
            True if started successfully, False otherwise
        """
        if self._started:
            return True

        try:
            PrintStyle.standard("Starting visual document Docker sidecar...")

            # Initialize Docker manager
            self._docker_manager = DockerContainerManager(
                image=self.IMAGE_NAME,
                name=self.CONTAINER_NAME,
                ports={"9010/tcp": self.SERVICE_PORT},
                volumes=self._get_volume_mounts()
            )

            # Start container
            self._docker_manager.start_container()

            # Determine service URL
            self._base_url = f"http://localhost:{self.SERVICE_PORT}"

            # Wait for service to be healthy
            healthy = await self._wait_for_health()
            if not healthy:
                PrintStyle.error("Docker sidecar failed health check")
                return False

            self._started = True
            PrintStyle.standard(f"Visual document Docker sidecar ready at {self._base_url}")
            return True

        except Exception as e:
            PrintStyle.error(f"Failed to start Docker sidecar: {e}")
            return False

    async def _wait_for_health(self) -> bool:
        """Wait for the service to become healthy."""
        if not self._base_url:
            return False

        start_time = asyncio.get_event_loop().time()
        timeout = self.HEALTH_CHECK_TIMEOUT

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self._base_url}/health",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            return True
            except Exception:
                pass

            await asyncio.sleep(2)

        return False

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Send HTTP request to the sidecar service.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint (e.g., "/index")
            json_data: Optional JSON body

        Returns:
            Response dict with 'success' and 'result' or 'error' keys
        """
        if not self._started or not self._base_url:
            if not await self.start():
                return {"success": False, "error": "Docker sidecar not available"}

        try:
            session = await self._get_session()
            url = f"{self._base_url}{endpoint}"

            async with session.request(
                method,
                url,
                json=json_data,
                timeout=aiohttp.ClientTimeout(total=300)  # 5 min for long ops
            ) as response:
                return await response.json()

        except asyncio.TimeoutError:
            return {"success": False, "error": "Request timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def index_document(
        self,
        uri: str,
        pdf_path: str,
        output_dir: str,
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Index a document via Docker sidecar."""
        return await self.request("POST", "/index", {
            "uri": uri,
            "pdf_path": pdf_path,
            "output_dir": output_dir,
            "settings": settings
        })

    async def search(
        self,
        query: str,
        document_uris: Optional[List[str]] = None,
        limit: int = 5,
        settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Search indexed documents via Docker sidecar."""
        return await self.request("POST", "/search", {
            "query": query,
            "document_uris": document_uris,
            "limit": limit,
            "settings": settings or {}
        })

    async def status(self) -> Dict[str, Any]:
        """Get sidecar status."""
        return await self.request("GET", "/status")

    async def shutdown(self) -> None:
        """Shutdown the Docker sidecar."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        if self._docker_manager and self._docker_manager.container:
            try:
                # Request graceful shutdown
                await self.request("POST", "/shutdown")
                await asyncio.sleep(1)
            except Exception:
                pass

            # Stop container
            self._docker_manager.cleanup_container()

        self._started = False
        self._base_url = None
        PrintStyle.standard("Visual document Docker sidecar stopped")

    def is_running(self) -> bool:
        """Check if sidecar is running."""
        return self._started and self._docker_manager is not None
```

**Step 2: Verify file exists**

Run: `ls -la python/helpers/visual_document_docker_service.py`
Expected: File exists with ~180 lines

**Step 3: Commit**

```bash
git add python/helpers/visual_document_docker_service.py
git commit -m "feat: add Docker sidecar service client for visual documents"
```

---

## Task 4: Add docker_sidecar Execution Mode to Settings

**Files:**
- Modify: `python/helpers/settings.py` (add docker_sidecar to Literal type)

**Step 1: Update the Literal type for execution mode**

Find the line:
```python
visual_doc_execution_mode: Literal["in_process", "subprocess"]
```

Change to:
```python
visual_doc_execution_mode: Literal["in_process", "subprocess", "docker_sidecar"]
```

**Step 2: Verify the change**

Run: `grep -n "visual_doc_execution_mode" python/helpers/settings.py`
Expected: Shows `Literal["in_process", "subprocess", "docker_sidecar"]`

**Step 3: Commit**

```bash
git add python/helpers/settings.py
git commit -m "feat: add docker_sidecar to visual_doc_execution_mode options"
```

---

## Task 5: Update VisualDocumentStore with Docker Sidecar Fallback

**Files:**
- Modify: `python/helpers/visual_document_query.py`
  - Update `_get_execution_mode()` to handle docker_sidecar
  - Update `_try_subprocess_with_fallback()` to try docker_sidecar first

**Step 1: Update _get_execution_mode method**

Find the `_get_execution_mode` method and update to handle docker_sidecar:

```python
def _get_execution_mode(self) -> str:
    """
    Get execution mode with fallback logic.

    Order: docker_sidecar → subprocess → in_process → error
    """
    if self._execution_mode is not None:
        return self._execution_mode

    settings = get_settings()
    configured_mode = settings.get('visual_doc_execution_mode', 'in_process')

    if configured_mode == 'docker_sidecar':
        # Check if Docker sidecar mode can work
        try:
            from python.helpers.visual_document_docker_service import VisualDocumentDockerService
            self._execution_mode = 'docker_sidecar'
        except ImportError:
            PrintStyle.warning(
                "Docker sidecar mode requested but service not available, "
                "falling back to subprocess"
            )
            configured_mode = 'subprocess'  # Fall through to subprocess check
            self._fallback_triggered = True

    if configured_mode == 'subprocess':
        # Check if subprocess mode can work
        try:
            from python.helpers.visual_document_service import VisualDocumentService
            self._execution_mode = 'subprocess'
        except ImportError:
            PrintStyle.warning(
                "Subprocess mode requested but service not available, "
                "falling back to in_process"
            )
            self._execution_mode = 'in_process'
            self._fallback_triggered = True
    else:
        self._execution_mode = configured_mode if configured_mode in ('in_process', 'docker_sidecar') else 'in_process'

    return self._execution_mode
```

**Step 2: Update _try_subprocess_with_fallback to try docker_sidecar first**

Rename method and update logic:

```python
async def _try_remote_with_fallback(
    self,
    operation: str,
    **kwargs
) -> Tuple[bool, Any]:
    """
    Try remote operation with fallback chain.

    Fallback order: docker_sidecar → subprocess → in_process

    Args:
        operation: 'index' or 'search'
        **kwargs: Operation arguments

    Returns:
        Tuple of (used_remote, result_or_error)
    """
    mode = self._get_execution_mode()

    # Try Docker sidecar first (if configured and not fallen back)
    if mode == 'docker_sidecar' and not self._fallback_triggered:
        try:
            from python.helpers.visual_document_docker_service import VisualDocumentDockerService
            service = VisualDocumentDockerService.get_instance()

            if operation == 'index':
                response = await service.index_document(**kwargs)
            elif operation == 'search':
                response = await service.search(**kwargs)
            else:
                return False, f"Unknown operation: {operation}"

            if response.get('success'):
                return True, response.get('result')
            else:
                error = response.get('error', 'Unknown error')
                PrintStyle.warning(
                    f"Docker sidecar {operation} failed: {error}, "
                    "falling back to subprocess"
                )
                self._fallback_triggered = True
                mode = 'subprocess'  # Try subprocess next

        except Exception as e:
            PrintStyle.warning(
                f"Docker sidecar error: {e}, falling back to subprocess"
            )
            self._fallback_triggered = True
            mode = 'subprocess'

    # Try subprocess (if configured or fell back from docker_sidecar)
    if mode == 'subprocess':
        try:
            from python.helpers.visual_document_service import VisualDocumentService
            service = VisualDocumentService.get_instance()

            if operation == 'index':
                response = await service.index_document(**kwargs)
            elif operation == 'search':
                response = await service.search(**kwargs)
            else:
                return False, f"Unknown operation: {operation}"

            if response.get('success'):
                return True, response.get('result')
            else:
                error = response.get('error', 'Unknown error')
                PrintStyle.warning(
                    f"Subprocess {operation} failed: {error}, "
                    "falling back to in_process"
                )
                self._fallback_triggered = True

        except Exception as e:
            PrintStyle.warning(
                f"Subprocess error: {e}, falling back to in_process"
            )
            self._fallback_triggered = True

    # Use in_process mode
    return False, None
```

**Step 3: Update calls to the renamed method**

In `index_document` and `search` methods, change:
- `await self._try_subprocess_with_fallback(...)`
- to `await self._try_remote_with_fallback(...)`

**Step 4: Run grep to verify changes**

Run: `grep -n "_try_remote_with_fallback\|docker_sidecar" python/helpers/visual_document_query.py`
Expected: Shows the new method and docker_sidecar references

**Step 5: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add docker_sidecar to execution mode fallback chain"
```

---

## Task 6: Update VisualDocumentQueryHelper Validation

**Files:**
- Modify: `python/helpers/visual_document_query.py`
  - Update execution mode validation in `__init__`
  - Add shutdown method for Docker sidecar

**Step 1: Update validation in __init__**

Find the validation block in `VisualDocumentQueryHelper.__init__`:

```python
# Validate execution mode
settings = get_settings()
execution_mode = settings.get('visual_doc_execution_mode', 'in_process')
if execution_mode not in ('in_process', 'subprocess'):
    PrintStyle.warning(
        f"Invalid visual_doc_execution_mode '{execution_mode}', "
        "using 'in_process'"
    )
```

Change to:

```python
# Validate execution mode
settings = get_settings()
execution_mode = settings.get('visual_doc_execution_mode', 'in_process')
if execution_mode not in ('in_process', 'subprocess', 'docker_sidecar'):
    PrintStyle.warning(
        f"Invalid visual_doc_execution_mode '{execution_mode}', "
        "using 'in_process'"
    )
```

**Step 2: Update shutdown_subprocess to also handle Docker sidecar**

Find the `shutdown_subprocess` method and update:

```python
@staticmethod
async def shutdown_subprocess() -> None:
    """
    Shutdown the subprocess worker or Docker sidecar if running.
    Call this on application shutdown.
    """
    # Shutdown subprocess worker
    try:
        from python.helpers.visual_document_service import VisualDocumentService
        service = VisualDocumentService.get_instance()
        await service.shutdown()
    except ImportError:
        pass  # Service not available

    # Shutdown Docker sidecar
    try:
        from python.helpers.visual_document_docker_service import VisualDocumentDockerService
        service = VisualDocumentDockerService.get_instance()
        await service.shutdown()
    except ImportError:
        pass  # Service not available
```

**Step 3: Verify changes**

Run: `grep -n "docker_sidecar\|shutdown" python/helpers/visual_document_query.py | head -20`
Expected: Shows docker_sidecar validation and shutdown handling Docker sidecar

**Step 4: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: update validation and shutdown for docker_sidecar mode"
```

---

## Task 7: Update Tool Prompt with Docker Sidecar Documentation

**Files:**
- Modify: `prompts/agent.system.tool.document_query.md`

**Step 1: Update execution modes documentation**

Find the execution modes section and update:

```markdown
### Execution Modes

Visual document query supports three execution modes configurable via settings:

- **in_process** (default): LitePali runs in the main process. Simple setup, uses main process memory.
- **subprocess**: LitePali runs in isolated subprocess. Better memory isolation, auto-fallback on failure.
- **docker_sidecar**: LitePali runs in dedicated Docker container. Maximum isolation, best for containerized deployments.

Fallback chain: docker_sidecar → subprocess → in_process

Configure via `visual_doc_execution_mode` setting.
```

**Step 2: Verify the change**

Run: `grep -A 10 "Execution Modes" prompts/agent.system.tool.document_query.md`
Expected: Shows all three execution modes with descriptions

**Step 3: Commit**

```bash
git add prompts/agent.system.tool.document_query.md
git commit -m "docs: add docker_sidecar to execution mode documentation"
```

---

## Task 8: Create Build Script for Docker Image

**Files:**
- Create: `docker/visual_document_service/build.sh`

**Step 1: Create the build script**

```bash
#!/bin/bash
# Build the visual document service Docker image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Copy the HTTP server to the build context
cp "$PROJECT_ROOT/python/helpers/visual_document_http_server.py" "$SCRIPT_DIR/server.py"

# Build the image
docker build -t agent0ai/visual-document-service:latest "$SCRIPT_DIR"

# Clean up copied file
rm -f "$SCRIPT_DIR/server.py"

echo "Build complete: agent0ai/visual-document-service:latest"
```

**Step 2: Make executable and verify**

Run: `chmod +x docker/visual_document_service/build.sh && ls -la docker/visual_document_service/`
Expected: build.sh is executable

**Step 3: Commit**

```bash
git add docker/visual_document_service/build.sh
git commit -m "feat: add build script for visual document Docker image"
```

---

## Task 9: Fix Dockerfile COPY Path Issue

**Files:**
- Modify: `docker/visual_document_service/Dockerfile`

The Dockerfile uses `COPY ../../python/...` which won't work because Docker can't access files outside the build context.

**Step 1: Update Dockerfile to copy from build context**

Change the COPY line from:
```dockerfile
COPY ../../python/helpers/visual_document_http_server.py /app/server.py
```

To:
```dockerfile
# Server file is copied by build.sh to build context
COPY server.py /app/server.py
```

**Step 2: Verify the change**

Run: `grep "COPY" docker/visual_document_service/Dockerfile`
Expected: Shows `COPY server.py /app/server.py`

**Step 3: Commit**

```bash
git add docker/visual_document_service/Dockerfile
git commit -m "fix: update Dockerfile to use build context for server.py"
```

---

## Task 10: Add curl to Dockerfile for Health Check

**Files:**
- Modify: `docker/visual_document_service/Dockerfile`

The HEALTHCHECK uses curl but the slim image doesn't have it installed.

**Step 1: Add curl to apt-get install**

Find:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*
```

Change to:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*
```

**Step 2: Verify the change**

Run: `grep -A 3 "apt-get install" docker/visual_document_service/Dockerfile`
Expected: Shows both poppler-utils and curl

**Step 3: Commit**

```bash
git add docker/visual_document_service/Dockerfile
git commit -m "fix: add curl to Dockerfile for health check"
```

---

## Task 11: Integration Test - Build and Test Docker Image

**Step 1: Build the Docker image**

Run: `cd docker/visual_document_service && ./build.sh`
Expected: Build completes successfully

**Step 2: Test the container starts**

Run: `docker run -d --name test-visual-doc -p 9010:9010 agent0ai/visual-document-service:latest && sleep 5 && curl http://localhost:9010/health && docker stop test-visual-doc && docker rm test-visual-doc`
Expected: Health check returns `{"status":"healthy",...}`

**Step 3: Verify Python imports work**

Run: `cd /Users/lazy/agent-zero-dev && python -c "from python.helpers.visual_document_docker_service import VisualDocumentDockerService; print('Import OK')"`
Expected: "Import OK"

---

## Summary

Phase 4 adds Docker sidecar execution mode for maximum isolation:

1. **HTTP Server** (`visual_document_http_server.py`) - FastAPI wrapper for worker
2. **Dockerfile** (`docker/visual_document_service/`) - Container definition
3. **Docker Client** (`visual_document_docker_service.py`) - Manages sidecar lifecycle
4. **Fallback Chain** - docker_sidecar → subprocess → in_process

The Docker sidecar is ideal for:
- Containerized deployments (Kubernetes, Docker Compose)
- Memory isolation from main Agent Zero process
- Consistent environment for LitePali dependencies
- Easy horizontal scaling (multiple sidecars)

After implementation, test with:
```python
# In settings
visual_doc_execution_mode = "docker_sidecar"

# Then use document_query tool with mode="visual"
```
