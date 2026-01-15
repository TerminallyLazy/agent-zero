"""
Visual document query helper using LitePali for layout-aware document retrieval.
"""
import os
import hashlib
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import urlparse

from python.helpers.print_style import PrintStyle
from python.helpers import files
from python.helpers.settings import get_settings


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
            raise ImportError(
                "LitePali not installed. Run: pip install litepali colpali-engine"
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
        images = pdf2image.convert_from_path(
            pdf_path,
            dpi=dpi,
            first_page=1,
            last_page=max_pages
        )

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

        callback = progress_callback or (lambda x: None)
        uri_normalized = self.normalize_uri(document_uri)
        doc_hash = self.get_document_hash(uri_normalized)

        # Check if already indexed
        index_dir = self.storage_path / "indexes" / doc_hash
        if (index_dir / "metadata.json").exists():
            callback(f"Document already indexed: {document_uri}")
            return True

        callback(f"Indexing document: {document_uri}")

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

            # Convert PDF to images
            callback("Converting PDF to images...")
            images_dir = index_dir / "images"

            dpi = settings.get('visual_doc_pdf_dpi', 144)

            image_paths = self.convert_pdf_to_images(pdf_path, images_dir, dpi)
            callback(f"Converted {len(image_paths)} pages")

            # Add images to LitePali
            callback("Processing images through vision model...")
            for i, img_path in enumerate(image_paths):
                self.litepali.add(ImageFile(
                    path=str(img_path),
                    document_id=doc_hash,
                    page_id=str(i + 1),
                    metadata={"uri": uri_normalized, "page": i + 1}
                ))

            # Process embeddings
            batch_size = settings.get('visual_doc_batch_size', 4)
            self.litepali.process(batch_size=batch_size)

            # Save metadata
            import json
            from datetime import datetime

            metadata = {
                "uri": uri_normalized,
                "hash": doc_hash,
                "page_count": len(image_paths),
                "indexed_at": datetime.now().isoformat(),
                "scope": self.scope
            }

            os.makedirs(index_dir, exist_ok=True)
            with open(index_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)

            callback(f"Indexed {len(image_paths)} pages successfully")
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
        self.agent = agent
        self.store = VisualDocumentStore(agent, scope="project")
        self.progress_callback = progress_callback or (lambda x: None)

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

        # Index all documents
        for uri in document_uris:
            await self.store.index_document(uri, self.progress_callback)
            await self.agent.handle_intervention()

        # Search for each query
        all_results = []
        for query in queries:
            self.progress_callback(f"Searching: {query}")
            matches = await self.store.search(query, document_uris, limit=5)

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
        await self.store.index_document(document_uri, self.progress_callback)

        uri_normalized = self.store.normalize_uri(document_uri)
        doc_hash = self.store.get_document_hash(uri_normalized)
        index_dir = self.store.storage_path / "indexes" / doc_hash

        import json
        metadata_path = index_dir / "metadata.json"

        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)
            return f"Document indexed: {metadata['page_count']} pages, indexed at {metadata['indexed_at']}"

        return "Document not indexed"