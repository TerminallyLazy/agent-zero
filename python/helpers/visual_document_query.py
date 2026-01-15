"""
Visual document query helper using LitePali for layout-aware document retrieval.
"""
import os
import hashlib
import asyncio
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from python.helpers.print_style import PrintStyle
from python.helpers import files
from python.helpers.settings import get_settings


class VisualDocumentError(Exception):
    """Base exception for visual document operations."""
    pass


class ConfigurationError(VisualDocumentError):
    """Raised when settings are invalid or missing."""
    pass


class ResourceLimitError(VisualDocumentError):
    """Raised when resource limits are exceeded."""
    pass


class ModelLoadError(VisualDocumentError):
    """Raised when the LitePali model fails to load."""
    pass


class IndexOperationError(VisualDocumentError):
    """Raised when index operations fail."""
    pass


class DocumentProcessingError(VisualDocumentError):
    """Raised when document processing (PDF conversion, download) fails."""
    pass


@dataclass
class ProgressStage:
    """Represents a stage in a multi-step operation."""
    name: str
    number: int
    total: int

    def format(self, detail: str = "", percent: int = 0) -> str:
        """Format progress message with stage info."""
        base = f"Stage {self.number}/{self.total}: {self.name}"
        if detail:
            base += f" - {detail}"
        if percent > 0:
            base += f" ({percent}%)"
        return base


class ProgressTracker:
    """Tracks and reports progress through multi-stage operations."""

    def __init__(self, callback: Optional[Callable[[str], None]] = None):
        self.callback = callback or (lambda x: None)
        self.current_stage: Optional[ProgressStage] = None

    def start_stage(self, name: str, number: int, total: int) -> None:
        """Start a new stage."""
        self.current_stage = ProgressStage(name, number, total)
        self.callback(self.current_stage.format())

    def update(self, detail: str = "", percent: int = 0) -> None:
        """Update current stage progress."""
        if self.current_stage:
            self.callback(self.current_stage.format(detail, percent))

    def complete(self) -> None:
        """Mark current operation as complete."""
        self.callback("Complete!")


@dataclass
class IndexEntry:
    """Entry in the index registry."""
    uri: str
    hash: str
    indexed_at: str
    page_count: int
    file_size_mb: float
    scope: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "IndexEntry":
        return cls(**data)


class IndexRegistry:
    """
    Central registry tracking all indexed documents.
    Persisted as JSON file in storage directory.
    """
    REGISTRY_FILE = "index_registry.json"

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.registry_path = storage_path / self.REGISTRY_FILE
        self._entries: Dict[str, IndexEntry] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load registry from disk."""
        if self._loaded:
            return
        self._load()

    def _load(self) -> None:
        """Load registry from JSON file."""
        import json
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r') as f:
                    data = json.load(f)
                    self._entries = {
                        uri: IndexEntry.from_dict(entry)
                        for uri, entry in data.items()
                    }
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                PrintStyle.error(f"Failed to load index registry: {e}")
                self._entries = {}
        self._loaded = True

    def _save(self) -> None:
        """Save registry to JSON file."""
        import json
        import tempfile
        os.makedirs(self.storage_path, exist_ok=True)
        # Write to temp file, then atomic rename
        fd, tmp_path = tempfile.mkstemp(dir=self.storage_path, suffix='.json')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(
                    {uri: entry.to_dict() for uri, entry in self._entries.items()},
                    f,
                    indent=2
                )
            os.replace(tmp_path, self.registry_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def add(self, entry: IndexEntry) -> None:
        """Add or update an entry."""
        self._ensure_loaded()
        self._entries[entry.uri] = entry
        self._save()

    def get(self, uri: str) -> Optional[IndexEntry]:
        """Get entry by URI."""
        self._ensure_loaded()
        return self._entries.get(uri)

    def remove(self, uri: str) -> bool:
        """Remove entry by URI. Returns True if found and removed."""
        self._ensure_loaded()
        if uri in self._entries:
            del self._entries[uri]
            self._save()
            return True
        return False

    def list_all(self) -> List[IndexEntry]:
        """List all entries."""
        self._ensure_loaded()
        return list(self._entries.values())

    def exists(self, uri: str) -> bool:
        """Check if URI is in registry."""
        self._ensure_loaded()
        return uri in self._entries


@dataclass
class VisualMatch:
    """Result from visual document search."""
    document_uri: str
    page_number: int
    score: float
    image_path: Path
    snippet: str  # OCR text if available


class VisualDocumentStore:
    """
    Manages LitePali indexes for visual document embeddings.
    Supports project-scoped and global storage.
    """

    GLOBAL_PATH = "usr/visual_docs"
    PROJECT_PATH = ".a0proj/visual_docs"

    def __init__(self, agent, scope: str = "project"):
        """
        Initialize store.

        Args:
            agent: Agent instance for context
            scope: "project" or "global"
        """
        self.agent = agent
        self.scope = scope
        self.storage_path = self._resolve_storage_path()
        self._litepali = None  # Lazy loaded
        self._index_loaded = False
        self.registry = IndexRegistry(self.storage_path)
        self._execution_mode: Optional[str] = None  # Will be resolved on first use
        self._fallback_triggered = False

    def _resolve_storage_path(self) -> Path:
        """Resolve storage path based on scope."""
        if self.scope == "global":
            base = files.get_abs_path(self.GLOBAL_PATH)
        else:
            # Project-scoped: use agent's work dir
            work_dir = getattr(self.agent, 'work_dir', None)
            if work_dir:
                base = os.path.join(work_dir, self.PROJECT_PATH)
            else:
                base = files.get_abs_path(self.PROJECT_PATH)

        os.makedirs(base, exist_ok=True)
        return Path(base)

    @property
    def litepali(self):
        """Lazy-load LitePali model."""
        if self._litepali is None:
            self._initialize_litepali()
        return self._litepali

    def _initialize_litepali(self):
        """Initialize LitePali with settings from agent config."""
        try:
            from litepali import LitePali
        except ImportError as e:
            raise ModelLoadError(
                "LitePali not installed. Install with: pip install litepali colpali-engine. "
                f"Original error: {e}"
            ) from e

        # Get settings from centralized settings system
        settings = get_settings()
        model_name = settings.get('visual_doc_model_name', "vidore/colpali-v1.2")

        PrintStyle.standard(f"Loading LitePali model: {model_name}")

        # Detect device
        import torch
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

        self._litepali = LitePali(model_name=model_name, device=device)
        PrintStyle.standard(f"LitePali loaded on {device}")

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
        elif self._execution_mode is None:
            self._execution_mode = 'in_process'

        return self._execution_mode

    async def _try_remote_with_fallback(
        self,
        operation: str,
        **kwargs
    ) -> Tuple[bool, Any]:
        """
        Try remote operation (docker_sidecar or subprocess) with fallback to in_process.

        Args:
            operation: 'index' or 'search'
            **kwargs: Operation arguments

        Returns:
            Tuple of (used_remote, result_or_error)
        """
        mode = self._get_execution_mode()

        # Try docker_sidecar first if configured
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
                    # Docker sidecar failed, trigger fallback to subprocess
                    error = response.get('error', 'Unknown error')
                    PrintStyle.warning(
                        f"Docker sidecar {operation} failed: {error}, "
                        "falling back to subprocess"
                    )
                    self._fallback_triggered = True
                    mode = 'subprocess'  # Fall through to subprocess

            except Exception as e:
                PrintStyle.warning(
                    f"Docker sidecar error: {e}, falling back to subprocess"
                )
                self._fallback_triggered = True
                mode = 'subprocess'  # Fall through to subprocess

        # Try subprocess if configured or fell back from docker_sidecar
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

    @staticmethod
    def get_document_hash(uri: str) -> str:
        """Generate consistent hash for document URI."""
        return hashlib.sha256(uri.encode()).hexdigest()[:12]

    @staticmethod
    def normalize_uri(uri: str) -> str:
        """Normalize document URI for consistent lookup."""
        normalized = uri.strip()
        parsed = urlparse(normalized)
        scheme = parsed.scheme or "file"

        if scheme == "file":
            path = files.fix_dev_path(
                normalized.removeprefix("file://").removeprefix("file:")
            )
            normalized = f"file://{path}"
        elif scheme in ["http", "https"]:
            normalized = normalized.replace("http://", "https://")

        return normalized

    def convert_pdf_to_images(
        self,
        pdf_path: str,
        output_dir: Path,
        dpi: int = 144
    ) -> List[Path]:
        """
        Convert PDF to images.

        Args:
            pdf_path: Path to PDF file
            output_dir: Directory to save images
            dpi: Resolution for conversion

        Returns:
            List of paths to generated images
        """
        import pdf2image

        os.makedirs(output_dir, exist_ok=True)

        # Get max pages from settings
        settings = get_settings()
        max_pages = settings.get('visual_doc_max_pages', 50)

        # Convert PDF to images
        try:
            images = pdf2image.convert_from_path(
                pdf_path,
                dpi=dpi,
                first_page=1,
                last_page=max_pages
            )
        except Exception as e:
            raise DocumentProcessingError(
                f"Failed to convert PDF to images: {e}. "
                "Ensure poppler-utils is installed (apt-get install poppler-utils)."
            ) from e

        image_paths = []
        for i, image in enumerate(images):
            image_path = output_dir / f"page_{i+1:03d}.png"
            image.save(image_path, "PNG")
            image_paths.append(image_path)

        return image_paths

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
        from litepali import ImageFile

        tracker = ProgressTracker(progress_callback)
        uri_normalized = self.normalize_uri(document_uri)
        doc_hash = self.get_document_hash(uri_normalized)

        # Check if already indexed (registry is source of truth)
        if self.registry.exists(uri_normalized):
            tracker.callback(f"Document already indexed: {document_uri}")
            return True

        # Stage 1: Locating document
        tracker.start_stage("Locating document", 1, 5)

        index_dir = self.storage_path / "indexes" / doc_hash

        # Download/copy document to temp location
        parsed = urlparse(uri_normalized)
        scheme = parsed.scheme or "file"

        import tempfile
        temp_pdf = None

        try:
            if scheme == "file":
                pdf_path = parsed.path
                tracker.update(f"Found local file: {pdf_path}")
            elif scheme in ["http", "https"]:
                import requests
                tracker.update("Downloading document...")
                response = requests.get(document_uri, timeout=30)
                response.raise_for_status()
                temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                temp_pdf.write(response.content)
                temp_pdf.close()
                pdf_path = temp_pdf.name
                tracker.update("Download complete")
            else:
                raise ValueError(f"Unsupported URI scheme: {scheme}")

            # Stage 2: Validating file
            tracker.start_stage("Validating file", 2, 5)
            settings = get_settings()
            max_size_mb = settings.get('visual_doc_max_file_size_mb', 50)
            file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
            if file_size_mb > max_size_mb:
                raise ResourceLimitError(
                    f"File too large ({file_size_mb:.1f}MB exceeds {max_size_mb}MB limit). "
                    f"Reduce document size or increase 'visual_doc_max_file_size_mb' setting."
                )
            tracker.update(f"File size: {file_size_mb:.1f}MB")

            # Try remote mode (docker_sidecar or subprocess) with fallback
            used_remote, result = await self._try_remote_with_fallback(
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

            if used_remote and result:
                # Remote service succeeded - stages 3-4 handled remotely
                tracker.start_stage("Processing through vision model", 4, 5)
                tracker.update(f"Indexed {result['page_count']} pages via remote service")
                page_count = result['page_count']

                # Stage 5: Save metadata and register
                tracker.start_stage("Saving index", 5, 5)
                from datetime import datetime

                indexed_at = datetime.now().isoformat()

                # Create registry entry
                entry = IndexEntry(
                    uri=uri_normalized,
                    hash=doc_hash,
                    indexed_at=indexed_at,
                    page_count=page_count,
                    file_size_mb=file_size_mb,
                    scope=self.scope
                )
                self.registry.add(entry)

                # Also save per-document metadata for backward compatibility
                import json
                metadata = entry.to_dict()
                os.makedirs(index_dir, exist_ok=True)
                with open(index_dir / "metadata.json", "w") as f:
                    json.dump(metadata, f, indent=2)

                tracker.complete()
                return True
            else:
                # Use in_process mode (existing code)
                # Stage 3: Convert PDF to images
                tracker.start_stage("Converting PDF to images", 3, 5)
                images_dir = index_dir / "images"

                dpi = settings.get('visual_doc_pdf_dpi', 144)

                image_paths = self.convert_pdf_to_images(pdf_path, images_dir, dpi)

                # Update progress during image save (already done in convert_pdf_to_images)
                for i in range(len(image_paths)):
                    tracker.update(f"Page {i+1}/{len(image_paths)}", int((i+1)/len(image_paths)*100))

                # Stage 4: Add images to LitePali
                tracker.start_stage("Processing through vision model", 4, 5)
                for i, img_path in enumerate(image_paths):
                    self.litepali.add(ImageFile(
                        path=str(img_path),
                        document_id=doc_hash,
                        page_id=str(i + 1),
                        metadata={"uri": uri_normalized, "page": i + 1}
                    ))
                    tracker.update(f"Page {i+1}/{len(image_paths)}", int((i+1)/len(image_paths)*100))

                # Process embeddings
                batch_size = settings.get('visual_doc_batch_size', 4)
                self.litepali.process(batch_size=batch_size)

                # Stage 5: Save metadata and register
                tracker.start_stage("Saving index", 5, 5)
                from datetime import datetime

                indexed_at = datetime.now().isoformat()

                # Create registry entry
                entry = IndexEntry(
                    uri=uri_normalized,
                    hash=doc_hash,
                    indexed_at=indexed_at,
                    page_count=len(image_paths),
                    file_size_mb=file_size_mb,
                    scope=self.scope
                )
                self.registry.add(entry)

                # Also save per-document metadata for backward compatibility
                import json
                metadata = entry.to_dict()
                os.makedirs(index_dir, exist_ok=True)
                with open(index_dir / "metadata.json", "w") as f:
                    json.dump(metadata, f, indent=2)

                tracker.complete()
                return True

        finally:
            if temp_pdf and os.path.exists(temp_pdf.name):
                os.unlink(temp_pdf.name)

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

        # Try remote mode (docker_sidecar or subprocess) with fallback
        used_remote, result = await self._try_remote_with_fallback(
            'search',
            query=query,
            document_uris=document_uris,
            limit=limit,
            settings={
                'model_name': settings.get('visual_doc_model_name', 'vidore/colpali-v1.2')
            }
        )

        if used_remote and result:
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

        # In-process mode (existing code follows)
        # Filter by document URIs if specified
        doc_hashes = None
        if document_uris:
            doc_hashes = [
                self.get_document_hash(self.normalize_uri(uri))
                for uri in document_uris
            ]

        # Search using LitePali
        results = self.litepali.search(query, k=limit * 2)  # Get extra for filtering

        matches = []
        for result in results:
            # Filter by document if specified
            if doc_hashes and result.document_id not in doc_hashes:
                continue

            match = VisualMatch(
                document_uri=result.metadata.get("uri", ""),
                page_number=int(result.metadata.get("page", 0)),
                score=result.score,
                image_path=Path(result.path),
                snippet=""  # Could add OCR here later
            )
            matches.append(match)

            if len(matches) >= limit:
                break

        return matches

    async def delete_document(
        self,
        document_uri: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Delete a document from the index.

        Args:
            document_uri: URI of document to delete
            progress_callback: Optional callback for progress updates

        Returns:
            True if deleted, False if not found
        """
        import shutil

        callback = progress_callback or (lambda x: None)
        uri_normalized = self.normalize_uri(document_uri)
        doc_hash = self.get_document_hash(uri_normalized)

        # Check if exists in registry
        if not self.registry.exists(uri_normalized):
            callback(f"Document not found in index: {document_uri}")
            return False

        callback(f"Deleting document: {document_uri}")

        # Remove from registry
        self.registry.remove(uri_normalized)

        # Remove index directory (embeddings + images)
        index_dir = self.storage_path / "indexes" / doc_hash
        if index_dir.exists():
            shutil.rmtree(index_dir)
            callback(f"Removed index directory: {index_dir}")

        callback("Document deleted successfully")
        return True

    def list_documents(self) -> List[IndexEntry]:
        """
        List all indexed documents.

        Returns:
            List of IndexEntry objects
        """
        return self.registry.list_all()

    async def reindex_document(
        self,
        document_uri: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Force re-indexing of a document.

        Args:
            document_uri: URI of document to reindex
            progress_callback: Optional callback for progress updates

        Returns:
            True if successful
        """
        callback = progress_callback or (lambda x: None)

        # Delete existing index
        await self.delete_document(document_uri, callback)

        # Re-index
        callback(f"Re-indexing document: {document_uri}")
        return await self.index_document(document_uri, callback)

    def get_disk_usage(self) -> dict:
        """
        Calculate disk usage for indexes.

        Returns:
            Dict with total_mb, document_count, and per-document breakdown
        """
        total_bytes = 0
        documents = []

        indexes_dir = self.storage_path / "indexes"
        if indexes_dir.exists():
            for doc_dir in indexes_dir.iterdir():
                if doc_dir.is_dir():
                    doc_size = sum(
                        f.stat().st_size
                        for f in doc_dir.rglob('*')
                        if f.is_file()
                    )
                    total_bytes += doc_size

                    # Try to get URI from registry
                    for entry in self.registry.list_all():
                        if entry.hash == doc_dir.name:
                            documents.append({
                                "uri": entry.uri,
                                "size_mb": doc_size / (1024 * 1024),
                                "page_count": entry.page_count
                            })
                            break

        return {
            "total_mb": total_bytes / (1024 * 1024),
            "document_count": len(documents),
            "documents": documents
        }

    def cleanup_orphaned_indexes(
        self,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> dict:
        """
        Remove index directories that are not in the registry.
        This can happen if indexing was interrupted or registry was corrupted.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with removed_count and freed_mb
        """
        import shutil

        callback = progress_callback or (lambda x: None)
        indexes_dir = self.storage_path / "indexes"

        if not indexes_dir.exists():
            return {"removed_count": 0, "freed_mb": 0.0}

        # Get all registered hashes
        registered_hashes = {entry.hash for entry in self.registry.list_all()}

        removed_count = 0
        freed_bytes = 0

        for doc_dir in indexes_dir.iterdir():
            if doc_dir.is_dir() and doc_dir.name not in registered_hashes:
                # Calculate size before removing
                dir_size = sum(
                    f.stat().st_size for f in doc_dir.rglob('*') if f.is_file()
                )

                callback(f"Removing orphaned index: {doc_dir.name}")
                try:
                    shutil.rmtree(doc_dir)
                    freed_bytes += dir_size
                    removed_count += 1
                except OSError as e:
                    callback(f"Failed to remove {doc_dir.name}: {e}")

        result = {
            "removed_count": removed_count,
            "freed_mb": freed_bytes / (1024 * 1024)
        }

        callback(f"Cleanup complete: removed {removed_count} orphans, freed {result['freed_mb']:.1f}MB")
        return result

    @staticmethod
    def get_stores(agent) -> tuple["VisualDocumentStore", "VisualDocumentStore"]:
        """
        Get both project and global stores.

        Returns:
            Tuple of (project_store, global_store)
        """
        return (
            VisualDocumentStore(agent, scope="project"),
            VisualDocumentStore(agent, scope="global")
        )

    @staticmethod
    def find_document(
        agent,
        document_uri: str
    ) -> tuple[Optional["VisualDocumentStore"], Optional[IndexEntry]]:
        """
        Find a document across project and global scopes.
        Checks project scope first, then global.

        Args:
            agent: Agent instance
            document_uri: Document URI to find

        Returns:
            Tuple of (store, entry) or (None, None) if not found
        """
        uri_normalized = VisualDocumentStore.normalize_uri(document_uri)

        # Check project scope first
        project_store = VisualDocumentStore(agent, scope="project")
        entry = project_store.registry.get(uri_normalized)
        if entry:
            return project_store, entry

        # Fall back to global scope
        global_store = VisualDocumentStore(agent, scope="global")
        entry = global_store.registry.get(uri_normalized)
        if entry:
            return global_store, entry

        return None, None


class VisualDocumentQueryHelper:
    """
    Main interface for visual document query tool.
    Handles document processing and visual Q&A.
    """

    @staticmethod
    def is_enabled() -> bool:
        """Check if visual document query is enabled in settings."""
        settings = get_settings()
        return settings.get('visual_doc_enabled', True)

    def __init__(
        self,
        agent,
        progress_callback: Optional[Callable[[str], None]] = None
    ):
        if not self.is_enabled():
            raise RuntimeError(
                "Visual document query is disabled. "
                "Set visual_doc_enabled=true in settings to enable."
            )

        # Validate execution mode
        settings = get_settings()
        execution_mode = settings.get('visual_doc_execution_mode', 'in_process')
        if execution_mode not in ('in_process', 'subprocess', 'docker_sidecar'):
            PrintStyle.warning(
                f"Invalid visual_doc_execution_mode '{execution_mode}', "
                "using 'in_process'"
            )

        self.agent = agent
        self.scope = "project"  # Default scope for new indexes
        self._project_store = VisualDocumentStore(agent, scope="project")
        self._global_store = VisualDocumentStore(agent, scope="global")
        self.progress_callback = progress_callback or (lambda x: None)

    def _get_store_for_document(self, document_uri: str) -> VisualDocumentStore:
        """
        Get the appropriate store for a document.
        If document exists, returns its store. Otherwise returns project store.
        """
        store, entry = VisualDocumentStore.find_document(self.agent, document_uri)
        if store:
            return store
        # Default to project store for new documents
        return self._project_store

    async def visual_document_qa(
        self,
        document_uris: List[str],
        queries: List[str]
    ) -> tuple[bool, str]:
        """
        Perform visual Q&A on documents.

        Args:
            document_uris: List of document URIs to query
            queries: List of questions to answer

        Returns:
            Tuple of (success, result_text)
        """
        self.progress_callback(f"Starting visual analysis for {len(document_uris)} documents")

        # Handle intervention (pause/resume)
        await self.agent.handle_intervention()

        # Index all documents (use existing store or project store for new)
        for uri in document_uris:
            store = self._get_store_for_document(uri)
            await store.index_document(uri, self.progress_callback)
            await self.agent.handle_intervention()

        # Search for each query (check project first, then global)
        all_results = []
        for query in queries:
            self.progress_callback(f"Searching: {query}")

            # Search project scope first
            matches = await self._project_store.search(query, document_uris, limit=5)

            # If not enough results, also search global
            if len(matches) < 5:
                global_matches = await self._global_store.search(
                    query, document_uris, limit=5 - len(matches)
                )
                matches.extend(global_matches)

            if matches:
                result_lines = [f"\n### Query: {query}\n"]
                for match in matches:
                    result_lines.append(
                        f"**Page {match.page_number}** (score: {match.score:.2f}) - {match.document_uri}"
                    )
                all_results.append("\n".join(result_lines))

            await self.agent.handle_intervention()

        if not all_results:
            return False, "No visual matches found in the documents."

        self.progress_callback("Visual analysis complete")
        return True, "\n".join(all_results)

    async def get_visual_summary(self, document_uri: str) -> str:
        """
        Get visual summary of a document (page count, indexed status).

        Args:
            document_uri: Document URI

        Returns:
            Summary text
        """
        # Get appropriate store for this document
        store = self._get_store_for_document(document_uri)
        await store.index_document(document_uri, self.progress_callback)

        uri_normalized = VisualDocumentStore.normalize_uri(document_uri)
        doc_hash = VisualDocumentStore.get_document_hash(uri_normalized)
        index_dir = store.storage_path / "indexes" / doc_hash

        import json
        metadata_path = index_dir / "metadata.json"

        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)
            return f"Document indexed: {metadata['page_count']} pages, indexed at {metadata['indexed_at']}"

        return "Document not indexed"

    def list_indexed_documents(self, scope: Optional[str] = None) -> str:
        """
        List all indexed documents.

        Args:
            scope: Optional filter - "project", "global", or None for both

        Returns:
            Formatted string listing documents
        """
        entries = []

        if scope in (None, "project"):
            for entry in self._project_store.list_documents():
                entries.append(("project", entry))

        if scope in (None, "global"):
            for entry in self._global_store.list_documents():
                entries.append(("global", entry))

        if not entries:
            return "No documents indexed."

        lines = ["## Indexed Documents\n"]
        for scope_name, entry in entries:
            lines.append(
                f"- **[{scope_name}]** {entry.uri}\n"
                f"  - Pages: {entry.page_count}, Size: {entry.file_size_mb:.1f}MB\n"
                f"  - Indexed: {entry.indexed_at}"
            )

        # Add disk usage summary
        project_usage = self._project_store.get_disk_usage()
        global_usage = self._global_store.get_disk_usage()
        total_mb = project_usage['total_mb'] + global_usage['total_mb']
        lines.append(f"\n**Total disk usage:** {total_mb:.1f}MB")

        return "\n".join(lines)

    async def delete_indexed_document(self, document_uri: str) -> str:
        """
        Delete a document from the index.

        Args:
            document_uri: URI of document to delete

        Returns:
            Status message
        """
        store, entry = VisualDocumentStore.find_document(self.agent, document_uri)

        if not store:
            return f"Document not found in index: {document_uri}"

        success = await store.delete_document(document_uri, self.progress_callback)
        if success:
            return f"Deleted: {document_uri} (was in {entry.scope} scope)"
        return f"Failed to delete: {document_uri}"

    async def reindex_indexed_document(
        self,
        document_uri: str,
        scope: Optional[str] = None
    ) -> str:
        """
        Force re-indexing of a document.

        Args:
            document_uri: URI of document to reindex
            scope: Target scope (uses existing or "project" if not specified)

        Returns:
            Status message
        """
        # Find existing scope or use specified/default
        existing_store, entry = VisualDocumentStore.find_document(self.agent, document_uri)

        if scope:
            target_store = self._project_store if scope == "project" else self._global_store
        elif existing_store:
            target_store = existing_store
        else:
            target_store = self._project_store

        # If moving to a different scope, delete from original scope first
        if existing_store and existing_store.scope != target_store.scope:
            await existing_store.delete_document(document_uri, self.progress_callback)

        success = await target_store.reindex_document(document_uri, self.progress_callback)
        if success:
            return f"Re-indexed: {document_uri} (in {target_store.scope} scope)"
        return f"Failed to re-index: {document_uri}"

    def cleanup_indexes(self) -> str:
        """
        Clean up orphaned indexes in both scopes.

        Returns:
            Status message
        """
        project_result = self._project_store.cleanup_orphaned_indexes(self.progress_callback)
        global_result = self._global_store.cleanup_orphaned_indexes(self.progress_callback)

        total_removed = project_result['removed_count'] + global_result['removed_count']
        total_freed = project_result['freed_mb'] + global_result['freed_mb']

        if total_removed == 0:
            return "No orphaned indexes found."

        return f"Cleaned up {total_removed} orphaned indexes, freed {total_freed:.1f}MB"

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