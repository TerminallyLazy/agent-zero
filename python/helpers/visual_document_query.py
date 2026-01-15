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

        # Get settings
        settings = self.agent.config if hasattr(self.agent, 'config') else {}
        model_name = getattr(settings, 'visual_doc_model_name', None) or "vidore/colpali-v1.2"

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
        settings = self.agent.config if hasattr(self.agent, 'config') else {}
        max_pages = getattr(settings, 'visual_doc_max_pages', None) or 50

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

            # Convert PDF to images
            callback("Converting PDF to images...")
            images_dir = index_dir / "images"

            settings = self.agent.config if hasattr(self.agent, 'config') else {}
            dpi = getattr(settings, 'visual_doc_pdf_dpi', None) or 144

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
            batch_size = getattr(settings, 'visual_doc_batch_size', None) or 4
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
