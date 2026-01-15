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
