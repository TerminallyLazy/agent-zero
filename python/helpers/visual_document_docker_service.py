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
    # Local image - must be built with: docker/visual_document_service/build.sh
    IMAGE_NAME = "a0-visual-document-service:local"
    CONTAINER_NAME = "a0-visual-document-service"
    SERVICE_PORT = 9010
    HEALTH_CHECK_TIMEOUT = 60  # seconds

    def __init__(self):
        self._docker_manager: Optional[DockerContainerManager] = None
        self._started = False
        self._base_url: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()

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
        async with self._lock:
            if self._started:
                return True

            try:
                PrintStyle.standard("Starting visual document Docker sidecar...")

                # Check if Docker image exists
                try:
                    import docker
                    client = docker.from_env()
                    client.images.get(self.IMAGE_NAME)
                except docker.errors.ImageNotFound:
                    PrintStyle.error(
                        f"Docker image '{self.IMAGE_NAME}' not found. "
                        "Build it first with: ./docker/visual_document_service/build.sh"
                    )
                    return False
                except Exception as docker_err:
                    PrintStyle.error(f"Docker not available: {docker_err}")
                    return False

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
        async with self._lock:
            # Close session with proper error handling
            if self._session is not None:
                try:
                    if not self._session.closed:
                        await self._session.close()
                except Exception:
                    pass
                finally:
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
        """Check if sidecar is running (basic check)."""
        return self._started and self._docker_manager is not None

    async def is_healthy(self) -> bool:
        """Check if sidecar is running and responding to health checks."""
        if not self._started or not self._base_url:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._base_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception:
            return False
