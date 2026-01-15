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
            return await self._start_unlocked()

    async def _start_unlocked(self) -> bool:
        """
        Internal start method that assumes lock is already held.

        Returns:
            True if started successfully, False otherwise
        """
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
                # Try to start if not running (use _start_unlocked since we already hold lock)
                if not await self._start_unlocked():
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
