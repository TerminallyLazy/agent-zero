# LitePali Phase 3: Process Isolation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add subprocess execution mode for LitePali to enable memory isolation and graceful degradation.

**Architecture:** Create a standalone worker process that handles LitePali operations via JSON-line protocol over stdin/stdout. A service class manages the subprocess lifecycle, with automatic fallback from subprocess to in-process mode when subprocess fails.

**Tech Stack:** Python subprocess, JSON-lines protocol, asyncio for async communication

---

## Overview

Phase 3 adds process isolation to the LitePali integration:

1. **visual_document_worker.py** - Standalone script running LitePali in isolated process
2. **VisualDocumentService** - Manager class for subprocess communication
3. **Execution modes** - `in_process` (current) and `subprocess` (new)
4. **Fallback chain** - subprocess → in_process → error
5. **Settings validation** - Ensure valid execution mode configuration

## Key Design Decisions

- **JSON-lines protocol**: Simple, debuggable, one JSON object per line
- **Async subprocess communication**: Non-blocking I/O with asyncio
- **Graceful degradation**: Auto-fallback to in-process when subprocess fails
- **Keep model loaded**: Worker stays alive between requests (configurable)

---

## Task 1: Add Execution Mode Settings

**Files:**
- Modify: `python/helpers/settings.py`

**Step 1: Add new settings to Settings TypedDict**

In `python/helpers/settings.py`, find the `Settings` class (around line 53) and add after line 157 (after `visual_doc_max_file_size_mb`):

```python
    visual_doc_execution_mode: str  # "in_process" or "subprocess"
    visual_doc_keep_model_loaded: bool  # Keep subprocess alive between requests
```

**Step 2: Add defaults in get_default_settings()**

Find `get_default_settings()` function (around line 460) and add after line 545 (after `visual_doc_max_file_size_mb`):

```python
        visual_doc_execution_mode=get_default_value("visual_doc_execution_mode", "in_process"),
        visual_doc_keep_model_loaded=get_default_value("visual_doc_keep_model_loaded", True),
```

**Step 3: Verify the changes compile**

Run:
```bash
cd /Users/lazy/agent-zero-dev/.worktrees/litepali-phase3 && python -c "from python.helpers.settings import get_settings; s = get_settings(); print(f'execution_mode: {s.get(\"visual_doc_execution_mode\")}')"
```

Expected: `execution_mode: in_process`

**Step 4: Commit**

```bash
git add python/helpers/settings.py
git commit -m "feat: add visual_doc_execution_mode and keep_model_loaded settings"
```

---

## Task 2: Create Visual Document Worker Script

**Files:**
- Create: `python/helpers/visual_document_worker.py`

**Step 1: Create the worker script**

Create `python/helpers/visual_document_worker.py`:

```python
#!/usr/bin/env python3
"""
Standalone worker process for LitePali visual document processing.

Communicates via JSON-lines protocol over stdin/stdout.

Request format:
    {"action": "index", "uri": "...", "pdf_path": "...", "settings": {...}}
    {"action": "search", "query": "...", "document_uris": [...], "limit": 5}
    {"action": "status"}
    {"action": "shutdown"}

Response format:
    {"success": true, "result": ...}
    {"success": false, "error": "..."}
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


class VisualDocumentWorker:
    """Worker that handles LitePali operations in isolation."""

    def __init__(self):
        self._litepali = None
        self._indexed_docs: Dict[str, dict] = {}  # doc_hash -> metadata
        self._model_name: Optional[str] = None

    def _log(self, message: str) -> None:
        """Log to stderr (stdout is reserved for protocol)."""
        print(f"[worker] {message}", file=sys.stderr, flush=True)

    def _send_response(self, success: bool, result: Any = None, error: str = None) -> None:
        """Send JSON response to stdout."""
        response = {"success": success}
        if result is not None:
            response["result"] = result
        if error is not None:
            response["error"] = error
        print(json.dumps(response), flush=True)

    def _ensure_litepali(self, model_name: str = "vidore/colpali-v1.2") -> None:
        """Initialize LitePali if not already loaded or model changed."""
        if self._litepali is not None and self._model_name == model_name:
            return

        self._log(f"Loading LitePali model: {model_name}")

        try:
            from litepali import LitePali
        except ImportError as e:
            raise ImportError(
                "LitePali not installed. Run: pip install litepali colpali-engine"
            ) from e

        import torch
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

        self._litepali = LitePali(model_name=model_name, device=device)
        self._model_name = model_name
        self._log(f"LitePali loaded on {device}")

    def handle_index(self, request: dict) -> dict:
        """Handle index request."""
        uri = request["uri"]
        pdf_path = request["pdf_path"]
        output_dir = Path(request["output_dir"])
        settings = request.get("settings", {})

        model_name = settings.get("model_name", "vidore/colpali-v1.2")
        dpi = settings.get("pdf_dpi", 144)
        max_pages = settings.get("max_pages", 50)
        batch_size = settings.get("batch_size", 4)

        self._ensure_litepali(model_name)

        from litepali import ImageFile
        import pdf2image

        # Convert PDF to images
        self._log(f"Converting PDF to images: {pdf_path}")
        images_dir = output_dir / "images"
        os.makedirs(images_dir, exist_ok=True)

        images = pdf2image.convert_from_path(
            pdf_path,
            dpi=dpi,
            first_page=1,
            last_page=max_pages
        )

        image_paths = []
        for i, image in enumerate(images):
            image_path = images_dir / f"page_{i+1:03d}.png"
            image.save(image_path, "PNG")
            image_paths.append(str(image_path))

        self._log(f"Converted {len(image_paths)} pages")

        # Index with LitePali
        import hashlib
        doc_hash = hashlib.sha256(uri.encode()).hexdigest()[:12]

        self._log("Processing images through vision model...")
        for i, img_path in enumerate(image_paths):
            self._litepali.add(ImageFile(
                path=img_path,
                document_id=doc_hash,
                page_id=str(i + 1),
                metadata={"uri": uri, "page": i + 1}
            ))

        self._litepali.process(batch_size=batch_size)

        self._indexed_docs[doc_hash] = {
            "uri": uri,
            "page_count": len(image_paths),
            "image_paths": image_paths
        }

        return {
            "doc_hash": doc_hash,
            "page_count": len(image_paths),
            "image_paths": image_paths
        }

    def handle_search(self, request: dict) -> List[dict]:
        """Handle search request."""
        query = request["query"]
        document_uris = request.get("document_uris")
        limit = request.get("limit", 5)
        settings = request.get("settings", {})

        model_name = settings.get("model_name", "vidore/colpali-v1.2")
        self._ensure_litepali(model_name)

        # Filter by document URIs if specified
        import hashlib
        doc_hashes = None
        if document_uris:
            doc_hashes = [
                hashlib.sha256(uri.encode()).hexdigest()[:12]
                for uri in document_uris
            ]

        results = self._litepali.search(query, k=limit * 2)

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

            if len(matches) >= limit:
                break

        return matches

    def handle_status(self) -> dict:
        """Handle status request."""
        return {
            "model_loaded": self._litepali is not None,
            "model_name": self._model_name,
            "indexed_documents": len(self._indexed_docs),
            "documents": list(self._indexed_docs.keys())
        }

    def handle_request(self, request: dict) -> None:
        """Process a single request."""
        action = request.get("action")

        try:
            if action == "index":
                result = self.handle_index(request)
                self._send_response(True, result=result)

            elif action == "search":
                result = self.handle_search(request)
                self._send_response(True, result=result)

            elif action == "status":
                result = self.handle_status()
                self._send_response(True, result=result)

            elif action == "shutdown":
                self._send_response(True, result="shutting down")
                sys.exit(0)

            else:
                self._send_response(False, error=f"Unknown action: {action}")

        except Exception as e:
            self._log(f"Error handling {action}: {e}")
            self._send_response(False, error=str(e))

    def run(self) -> None:
        """Main loop - read JSON requests from stdin, write responses to stdout."""
        self._log("Worker started, waiting for requests...")

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                self.handle_request(request)
            except json.JSONDecodeError as e:
                self._send_response(False, error=f"Invalid JSON: {e}")


def main():
    """Entry point for worker process."""
    worker = VisualDocumentWorker()
    worker.run()


if __name__ == "__main__":
    main()
```

**Step 2: Test the worker can be imported**

Run:
```bash
cd /Users/lazy/agent-zero-dev/.worktrees/litepali-phase3 && python -c "from python.helpers.visual_document_worker import VisualDocumentWorker; print('Worker module OK')"
```

Expected: `Worker module OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_worker.py
git commit -m "feat: add visual_document_worker.py for subprocess mode"
```

---

## Task 3: Create VisualDocumentService Class

**Files:**
- Create: `python/helpers/visual_document_service.py`

**Step 1: Create the service class**

Create `python/helpers/visual_document_service.py`:

```python
"""
Service class for managing LitePali subprocess communication.

Handles spawning, communication, and lifecycle of the visual document worker.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from python.helpers.print_style import PrintStyle


class VisualDocumentService:
    """
    Manages LitePali in an isolated subprocess.

    Communicates via JSON-lines protocol over stdin/stdout.
    """

    _instance: Optional["VisualDocumentService"] = None

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self._lock = asyncio.Lock()
        self._started = False

    @classmethod
    def get_instance(cls) -> "VisualDocumentService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(self) -> bool:
        """
        Start the worker subprocess.

        Returns:
            True if started successfully, False otherwise
        """
        async with self._lock:
            if self._started and self.process and self.process.poll() is None:
                return True  # Already running

            try:
                # Find the worker script
                worker_module = "python.helpers.visual_document_worker"

                PrintStyle.standard(f"Starting visual document worker subprocess...")

                self.process = subprocess.Popen(
                    [sys.executable, "-m", worker_module],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                    cwd=os.getcwd()
                )

                self._started = True
                PrintStyle.standard("Visual document worker started")

                # Start stderr reader task
                asyncio.create_task(self._read_stderr())

                return True

            except Exception as e:
                PrintStyle.error(f"Failed to start worker: {e}")
                self._started = False
                return False

    async def _read_stderr(self) -> None:
        """Read and log stderr from worker process."""
        if not self.process or not self.process.stderr:
            return

        try:
            while self.process.poll() is None:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, self.process.stderr.readline
                )
                if line:
                    PrintStyle.standard(f"[worker] {line.strip()}")
        except Exception:
            pass  # Process may have terminated

    async def request(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        Send a request to the worker and await response.

        Args:
            action: The action to perform (index, search, status, shutdown)
            **kwargs: Additional arguments for the action

        Returns:
            Response dict with 'success' and 'result' or 'error' keys
        """
        async with self._lock:
            if not self._started or not self.process or self.process.poll() is not None:
                # Try to start if not running
                if not await self.start():
                    return {"success": False, "error": "Worker not available"}

            try:
                # Build request
                request = {"action": action, **kwargs}
                request_json = json.dumps(request) + "\n"

                # Send request
                self.process.stdin.write(request_json)
                self.process.stdin.flush()

                # Read response (with timeout)
                loop = asyncio.get_event_loop()
                response_line = await asyncio.wait_for(
                    loop.run_in_executor(None, self.process.stdout.readline),
                    timeout=300  # 5 minute timeout for long operations
                )

                if not response_line:
                    return {"success": False, "error": "No response from worker"}

                return json.loads(response_line)

            except asyncio.TimeoutError:
                return {"success": False, "error": "Worker request timed out"}
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Invalid response: {e}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def index_document(
        self,
        uri: str,
        pdf_path: str,
        output_dir: str,
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Index a document via subprocess.

        Args:
            uri: Document URI
            pdf_path: Path to PDF file
            output_dir: Directory for index output
            settings: Visual doc settings dict

        Returns:
            Response with doc_hash, page_count, image_paths
        """
        return await self.request(
            "index",
            uri=uri,
            pdf_path=pdf_path,
            output_dir=output_dir,
            settings=settings
        )

    async def search(
        self,
        query: str,
        document_uris: Optional[List[str]] = None,
        limit: int = 5,
        settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Search indexed documents via subprocess.

        Args:
            query: Search query
            document_uris: Optional filter by document URIs
            limit: Maximum results
            settings: Visual doc settings dict

        Returns:
            Response with list of matches
        """
        return await self.request(
            "search",
            query=query,
            document_uris=document_uris,
            limit=limit,
            settings=settings or {}
        )

    async def status(self) -> Dict[str, Any]:
        """Get worker status."""
        return await self.request("status")

    async def shutdown(self) -> None:
        """Gracefully shutdown the worker subprocess."""
        async with self._lock:
            if self.process and self.process.poll() is None:
                try:
                    # Try graceful shutdown
                    self.process.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
                    self.process.stdin.flush()

                    # Wait briefly for graceful exit
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.terminate()
                        self.process.wait(timeout=2)
                except Exception:
                    # Force kill if needed
                    try:
                        self.process.kill()
                    except Exception:
                        pass

            self._started = False
            self.process = None
            PrintStyle.standard("Visual document worker stopped")

    def is_running(self) -> bool:
        """Check if worker is running."""
        return self._started and self.process is not None and self.process.poll() is None
```

**Step 2: Test the service can be imported**

Run:
```bash
cd /Users/lazy/agent-zero-dev/.worktrees/litepali-phase3 && python -c "from python.helpers.visual_document_service import VisualDocumentService; print('Service module OK')"
```

Expected: `Service module OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_service.py
git commit -m "feat: add VisualDocumentService for subprocess management"
```

---

## Task 4: Add Fallback Chain Logic to VisualDocumentStore

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add execution mode property and fallback state**

In `python/helpers/visual_document_query.py`, find the `VisualDocumentStore.__init__` method (around line 140) and modify to add fallback tracking:

After line 153 (`self.registry = IndexRegistry(self.storage_path)`), add:

```python
        self._execution_mode: Optional[str] = None  # Will be resolved on first use
        self._fallback_triggered = False
```

**Step 2: Add execution mode resolution method**

After the `_initialize_litepali` method (ends around line 197), add:

```python
    def _get_execution_mode(self) -> str:
        """
        Get execution mode with fallback logic.

        Order: configured mode → fallback to in_process → error
        """
        if self._execution_mode is not None:
            return self._execution_mode

        settings = get_settings()
        configured_mode = settings.get('visual_doc_execution_mode', 'in_process')

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
            self._execution_mode = 'in_process'

        return self._execution_mode

    async def _try_subprocess_with_fallback(
        self,
        operation: str,
        **kwargs
    ) -> tuple[bool, Any]:
        """
        Try subprocess operation with fallback to in_process.

        Args:
            operation: 'index' or 'search'
            **kwargs: Operation arguments

        Returns:
            Tuple of (used_subprocess, result_or_error)
        """
        mode = self._get_execution_mode()

        if mode == 'subprocess' and not self._fallback_triggered:
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
                    # Subprocess failed, trigger fallback
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

**Step 3: Modify index_document to support execution modes**

Find the `index_document` method (starts around line 262). Replace the entire method with:

```python
    async def index_document(
        self,
        document_uri: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Index a document for visual search.

        Args:
            document_uri: URI of document (file:// or https://)
            progress_callback: Optional callback for progress updates

        Returns:
            True if successful
        """
        callback = progress_callback or (lambda x: None)
        uri_normalized = self.normalize_uri(document_uri)
        doc_hash = self.get_document_hash(uri_normalized)

        # Check if already indexed (registry is source of truth)
        if self.registry.exists(uri_normalized):
            callback(f"Document already indexed: {document_uri}")
            return True

        callback(f"Indexing document: {document_uri}")

        index_dir = self.storage_path / "indexes" / doc_hash

        # Download/copy document to temp location
        parsed = urlparse(uri_normalized)
        scheme = parsed.scheme or "file"

        import tempfile
        temp_pdf = None

        try:
            if scheme == "file":
                pdf_path = parsed.path
            elif scheme in ["http", "https"]:
                import requests
                callback("Downloading document...")
                response = requests.get(document_uri, timeout=30)
                response.raise_for_status()
                temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                temp_pdf.write(response.content)
                temp_pdf.close()
                pdf_path = temp_pdf.name
            else:
                raise ValueError(f"Unsupported URI scheme: {scheme}")

            # Validate file size
            settings = get_settings()
            max_size_mb = settings.get('visual_doc_max_file_size_mb', 50)
            file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
            if file_size_mb > max_size_mb:
                raise ValueError(
                    f"File size ({file_size_mb:.1f}MB) exceeds maximum allowed "
                    f"({max_size_mb}MB). Adjust visual_doc_max_file_size_mb in settings."
                )

            # Try subprocess mode with fallback
            used_subprocess, result = await self._try_subprocess_with_fallback(
                'index',
                uri=uri_normalized,
                pdf_path=pdf_path,
                output_dir=str(index_dir),
                settings={
                    'model_name': settings.get('visual_doc_model_name', 'vidore/colpali-v1.2'),
                    'pdf_dpi': settings.get('visual_doc_pdf_dpi', 144),
                    'max_pages': settings.get('visual_doc_max_pages', 50),
                    'batch_size': settings.get('visual_doc_batch_size', 4)
                }
            )

            if used_subprocess and result:
                # Subprocess succeeded
                callback(f"Indexed {result['page_count']} pages via subprocess")
                page_count = result['page_count']
            else:
                # Use in_process mode
                from litepali import ImageFile

                callback("Converting PDF to images...")
                images_dir = index_dir / "images"
                dpi = settings.get('visual_doc_pdf_dpi', 144)
                image_paths = self.convert_pdf_to_images(pdf_path, images_dir, dpi)
                callback(f"Converted {len(image_paths)} pages")

                callback("Processing images through vision model...")
                for i, img_path in enumerate(image_paths):
                    self.litepali.add(ImageFile(
                        path=str(img_path),
                        document_id=doc_hash,
                        page_id=str(i + 1),
                        metadata={"uri": uri_normalized, "page": i + 1}
                    ))

                batch_size = settings.get('visual_doc_batch_size', 4)
                self.litepali.process(batch_size=batch_size)
                page_count = len(image_paths)
                callback(f"Indexed {page_count} pages")

            # Save metadata and register
            from datetime import datetime
            indexed_at = datetime.now().isoformat()

            entry = IndexEntry(
                uri=uri_normalized,
                hash=doc_hash,
                indexed_at=indexed_at,
                page_count=page_count,
                file_size_mb=file_size_mb,
                scope=self.scope
            )
            self.registry.add(entry)

            # Save per-document metadata
            import json
            metadata = entry.to_dict()
            os.makedirs(index_dir, exist_ok=True)
            with open(index_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)

            callback(f"Indexed {page_count} pages successfully")
            return True

        finally:
            if temp_pdf and os.path.exists(temp_pdf.name):
                os.unlink(temp_pdf.name)
```

**Step 4: Modify search to support execution modes**

Find the `search` method (starts around line 377). Replace the method with:

```python
    async def search(
        self,
        query: str,
        document_uris: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[VisualMatch]:
        """
        Search indexed documents visually.

        Args:
            query: Search query
            document_uris: Optional list of URIs to search within
            limit: Maximum results to return

        Returns:
            List of VisualMatch results
        """
        settings = get_settings()

        # Try subprocess mode with fallback
        used_subprocess, result = await self._try_subprocess_with_fallback(
            'search',
            query=query,
            document_uris=document_uris,
            limit=limit,
            settings={
                'model_name': settings.get('visual_doc_model_name', 'vidore/colpali-v1.2')
            }
        )

        if used_subprocess and result:
            # Convert subprocess results to VisualMatch objects
            return [
                VisualMatch(
                    document_uri=m['document_uri'],
                    page_number=m['page_number'],
                    score=m['score'],
                    image_path=Path(m['image_path']),
                    snippet=""
                )
                for m in result
            ]

        # In-process mode
        doc_hashes = None
        if document_uris:
            doc_hashes = [
                self.get_document_hash(self.normalize_uri(uri))
                for uri in document_uris
            ]

        results = self.litepali.search(query, k=limit * 2)

        matches = []
        for result in results:
            if doc_hashes and result.document_id not in doc_hashes:
                continue

            match = VisualMatch(
                document_uri=result.metadata.get("uri", ""),
                page_number=int(result.metadata.get("page", 0)),
                score=result.score,
                image_path=Path(result.path),
                snippet=""
            )
            matches.append(match)

            if len(matches) >= limit:
                break

        return matches
```

**Step 5: Test the changes compile**

Run:
```bash
cd /Users/lazy/agent-zero-dev/.worktrees/litepali-phase3 && python -c "from python.helpers.visual_document_query import VisualDocumentStore; print('Fallback logic OK')"
```

Expected: `Fallback logic OK`

**Step 6: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add subprocess execution mode with fallback chain"
```

---

## Task 5: Add Settings Validation

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add validation to VisualDocumentQueryHelper**

In `python/helpers/visual_document_query.py`, find the `VisualDocumentQueryHelper.__init__` method (around line 644). After the `is_enabled()` check (line 649-653), add validation:

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

**Step 2: Test the validation**

Run:
```bash
cd /Users/lazy/agent-zero-dev/.worktrees/litepali-phase3 && python -c "
from python.helpers.settings import get_settings
from python.helpers.visual_document_query import VisualDocumentQueryHelper

settings = get_settings()
print(f'Execution mode: {settings.get(\"visual_doc_execution_mode\")}')
print('Validation OK')
"
```

Expected: Shows execution mode and `Validation OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add execution mode validation in VisualDocumentQueryHelper"
```

---

## Task 6: Add Subprocess Shutdown on Process Exit

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add cleanup method to VisualDocumentQueryHelper**

At the end of the `VisualDocumentQueryHelper` class (after `cleanup_indexes` method around line 865), add:

```python
    @staticmethod
    async def shutdown_subprocess() -> None:
        """
        Shutdown the subprocess worker if running.
        Call this on application shutdown.
        """
        try:
            from python.helpers.visual_document_service import VisualDocumentService
            service = VisualDocumentService.get_instance()
            await service.shutdown()
        except ImportError:
            pass  # Service not available
```

**Step 2: Test the cleanup method**

Run:
```bash
cd /Users/lazy/agent-zero-dev/.worktrees/litepali-phase3 && python -c "
import asyncio
from python.helpers.visual_document_query import VisualDocumentQueryHelper
asyncio.run(VisualDocumentQueryHelper.shutdown_subprocess())
print('Shutdown method OK')
"
```

Expected: `Shutdown method OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add subprocess shutdown method for cleanup"
```

---

## Task 7: Update Tool Prompt with Execution Mode Info

**Files:**
- Modify: `prompts/agent.system.tool.document_query.md`

**Step 1: Add execution mode documentation**

Open `prompts/agent.system.tool.document_query.md` and add after the visual mode examples section:

```markdown
### Execution Modes

Visual document query supports two execution modes configurable via settings:

- **in_process** (default): LitePali runs in the main process. Fast startup, shared memory.
- **subprocess**: LitePali runs in isolated process. Better memory isolation, auto-fallback on failure.

The system automatically falls back to in_process mode if subprocess mode fails.
```

**Step 2: Commit**

```bash
git add prompts/agent.system.tool.document_query.md
git commit -m "docs: add execution mode documentation to tool prompt"
```

---

## Task 8: Integration Test

**Step 1: Create a simple integration test**

Run the following to verify everything works together:

```bash
cd /Users/lazy/agent-zero-dev/.worktrees/litepali-phase3 && python -c "
import asyncio
from python.helpers.settings import get_settings
from python.helpers.visual_document_query import VisualDocumentStore, VisualDocumentQueryHelper

# Test settings
settings = get_settings()
print(f'✓ Settings loaded')
print(f'  - execution_mode: {settings.get(\"visual_doc_execution_mode\")}')
print(f'  - keep_model_loaded: {settings.get(\"visual_doc_keep_model_loaded\")}')

# Test imports
from python.helpers.visual_document_worker import VisualDocumentWorker
print(f'✓ Worker module imported')

from python.helpers.visual_document_service import VisualDocumentService
print(f'✓ Service module imported')

# Test service singleton
service = VisualDocumentService.get_instance()
print(f'✓ Service singleton created')
print(f'  - is_running: {service.is_running()}')

# Test store creation
class MockAgent:
    work_dir = '/tmp'
store = VisualDocumentStore(MockAgent(), scope='project')
print(f'✓ Store created')
print(f'  - execution_mode: {store._get_execution_mode()}')

print('\\n✓ All integration checks passed!')
"
```

Expected: All checks should pass

**Step 2: Commit the integration test as documentation**

No commit needed - this was just a verification step.

---

## Summary

Phase 3 adds:

1. **New settings**: `visual_doc_execution_mode` and `visual_doc_keep_model_loaded`
2. **Worker script**: `python/helpers/visual_document_worker.py` - standalone LitePali process
3. **Service class**: `python/helpers/visual_document_service.py` - subprocess manager
4. **Fallback chain**: subprocess → in_process with automatic fallback on failure
5. **Validation**: Execution mode validation in helper class
6. **Cleanup**: Shutdown method for graceful subprocess termination

The implementation maintains backward compatibility - default mode is `in_process` which works exactly as before.
