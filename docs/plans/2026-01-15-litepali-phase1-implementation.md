# LitePali Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add visual document query mode to existing `document_query` tool with in-process LitePali integration.

**Architecture:** Extend `document_query` tool with `mode` parameter ("text"/"visual"/"auto"). Visual mode uses LitePali for layout-aware document retrieval. Results from both pipelines returned as separate labeled sections.

**Tech Stack:** LitePali, ColPali-engine, pdf2image (existing), safetensors

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

**Step 1: Add LitePali dependencies**

Add to end of `requirements.txt`:
```txt
litepali>=0.0.5
colpali-engine>=0.3.0,<0.4.0
safetensors>=0.4.0
```

**Step 2: Verify dependencies can be resolved**

Run: `pip install litepali colpali-engine safetensors --dry-run 2>&1 | tail -5`
Expected: Shows packages that would be installed (no conflicts)

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add litepali and colpali-engine for visual document query"
```

---

## Task 2: Add Settings for Visual Document Query

**Files:**
- Modify: `python/helpers/settings.py:53-149` (Settings TypedDict)
- Modify: `python/helpers/settings.py:452-532` (get_default_settings)

**Step 1: Add type definitions to Settings TypedDict**

After line 148 (`update_check_enabled: bool`), add:
```python
    # Visual document query settings
    visual_doc_enabled: bool
    visual_doc_model_name: str
    visual_doc_batch_size: int
    visual_doc_pdf_dpi: int
    visual_doc_max_pages: int
    visual_doc_max_file_size_mb: int
```

**Step 2: Add defaults to get_default_settings()**

Before the closing paren of `get_default_settings()` (around line 531), add:
```python
        visual_doc_enabled=get_default_value("visual_doc_enabled", True),
        visual_doc_model_name=get_default_value("visual_doc_model_name", "vidore/colpali-v1.2"),
        visual_doc_batch_size=get_default_value("visual_doc_batch_size", 4),
        visual_doc_pdf_dpi=get_default_value("visual_doc_pdf_dpi", 144),
        visual_doc_max_pages=get_default_value("visual_doc_max_pages", 50),
        visual_doc_max_file_size_mb=get_default_value("visual_doc_max_file_size_mb", 50),
```

**Step 3: Verify settings load without error**

Run: `cd /Users/lazy/agent-zero-dev/.worktrees/litepali-impl && python -c "from python.helpers.settings import get_default_settings; s = get_default_settings(); print(s.get('visual_doc_enabled'))"`
Expected: `True`

**Step 4: Commit**

```bash
git add python/helpers/settings.py
git commit -m "feat(settings): add visual document query configuration options"
```

---

## Task 3: Create VisualDocumentStore Class (Skeleton)

**Files:**
- Create: `python/helpers/visual_document_query.py`

**Step 1: Create the helper file with imports and dataclass**

```python
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
```

**Step 2: Verify file loads without syntax errors**

Run: `cd /Users/lazy/agent-zero-dev/.worktrees/litepali-impl && python -c "from python.helpers.visual_document_query import VisualDocumentStore, VisualMatch; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add VisualDocumentStore skeleton and VisualMatch dataclass"
```

---

## Task 4: Implement LitePali Lazy Loading

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add lazy loading property and initialization method**

Add after `_resolve_storage_path` method:
```python
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
```

**Step 2: Verify lazy loading compiles**

Run: `cd /Users/lazy/agent-zero-dev/.worktrees/litepali-impl && python -c "from python.helpers.visual_document_query import VisualDocumentStore; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add lazy loading for LitePali model with device detection"
```

---

## Task 5: Implement PDF-to-Image Conversion

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add PDF conversion method**

Add to `VisualDocumentStore` class:
```python
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
```

**Step 2: Verify method compiles**

Run: `cd /Users/lazy/agent-zero-dev/.worktrees/litepali-impl && python -c "from python.helpers.visual_document_query import VisualDocumentStore; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add PDF-to-image conversion using pdf2image"
```

---

## Task 6: Implement Document Indexing

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add index_document method**

Add to `VisualDocumentStore` class:
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
```

**Step 2: Verify method compiles**

Run: `cd /Users/lazy/agent-zero-dev/.worktrees/litepali-impl && python -c "from python.helpers.visual_document_query import VisualDocumentStore; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: implement document indexing with LitePali"
```

---

## Task 7: Implement Visual Search

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add search method**

Add to `VisualDocumentStore` class:
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
```

**Step 2: Verify method compiles**

Run: `cd /Users/lazy/agent-zero-dev/.worktrees/litepali-impl && python -c "from python.helpers.visual_document_query import VisualDocumentStore; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: implement visual search with LitePali"
```

---

## Task 8: Create VisualDocumentQueryHelper

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add helper class at end of file**

```python
class VisualDocumentQueryHelper:
    """
    Main interface for visual document query tool.
    Handles document processing and visual Q&A.
    """

    def __init__(
        self,
        agent,
        progress_callback: Optional[Callable[[str], None]] = None
    ):
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

        # Handle intervention if agent supports it
        if hasattr(self.agent, 'handle_intervention'):
            await self.agent.handle_intervention()

        # Index all documents
        for uri in document_uris:
            await self.store.index_document(uri, self.progress_callback)
            if hasattr(self.agent, 'handle_intervention'):
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

            if hasattr(self.agent, 'handle_intervention'):
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
```

**Step 2: Verify helper compiles**

Run: `cd /Users/lazy/agent-zero-dev/.worktrees/litepali-impl && python -c "from python.helpers.visual_document_query import VisualDocumentQueryHelper; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add VisualDocumentQueryHelper for tool integration"
```

---

## Task 9: Add Mode Parameter to Document Query Tool

**Files:**
- Modify: `python/tools/document_query.py`

**Step 1: Update imports and add mode handling**

Replace entire file content:
```python
import asyncio

from python.helpers.tool import Tool, Response
from python.helpers.document_query import DocumentQueryHelper


class DocumentQueryTool(Tool):

    async def execute(self, **kwargs):
        document_uri = kwargs.get("document")
        document_uris = []

        if isinstance(document_uri, list):
            document_uris = document_uri
        elif isinstance(document_uri, str):
            document_uris = [document_uri]

        if not document_uris:
            return Response(message="Error: no document provided", break_loop=False)

        queries = (
            kwargs["queries"]
            if "queries" in kwargs
            else [kwargs["query"]]
            if ("query" in kwargs and kwargs["query"])
            else []
        )

        # Get mode parameter (default to "text" for backward compatibility)
        mode = kwargs.get("mode", "text")
        if mode not in ("text", "visual", "auto"):
            mode = "text"

        try:
            progress = []

            def progress_callback(msg):
                progress.append(msg)
                self.log.update(progress="\n".join(progress))

            results = []

            # Text mode (original behavior)
            if mode in ("text", "auto"):
                text_helper = DocumentQueryHelper(self.agent, progress_callback)
                if not queries:
                    contents = await asyncio.gather(
                        *[text_helper.document_get_content(uri) for uri in document_uris]
                    )
                    text_content = "\n\n---\n\n".join(contents)
                else:
                    _, text_content = await text_helper.document_qa(document_uris, queries)

                if mode == "auto":
                    results.append("## Text Results\n\n" + text_content)
                else:
                    results.append(text_content)

            # Visual mode
            if mode in ("visual", "auto"):
                try:
                    from python.helpers.visual_document_query import VisualDocumentQueryHelper

                    visual_helper = VisualDocumentQueryHelper(self.agent, progress_callback)

                    if not queries:
                        # Get visual summary for each document
                        summaries = []
                        for uri in document_uris:
                            summary = await visual_helper.get_visual_summary(uri)
                            summaries.append(f"{uri}: {summary}")
                        visual_content = "\n".join(summaries)
                    else:
                        _, visual_content = await visual_helper.visual_document_qa(
                            document_uris, queries
                        )

                    if mode == "auto":
                        results.append("## Visual Results\n\n" + visual_content)
                    else:
                        results.append(visual_content)

                except ImportError:
                    if mode == "visual":
                        return Response(
                            message="Error: Visual mode requires litepali. Install with: pip install litepali",
                            break_loop=False
                        )
                    # In auto mode, just skip visual if not available
                    progress_callback("Visual mode not available (litepali not installed)")

            # Combine results
            if mode == "auto" and len(results) > 1:
                content = "\n\n---\n\n".join(results)
                content += "\n\n---\n*Note: Both text and visual analysis provided. Visual results may capture layout-dependent information that text extraction missed.*"
            else:
                content = results[0] if results else "No results"

            return Response(message=content, break_loop=False)

        except Exception as e:  # pylint: disable=broad-exception-caught
            return Response(message=f"Error processing document: {e}", break_loop=False)
```

**Step 2: Verify tool compiles**

Run: `cd /Users/lazy/agent-zero-dev/.worktrees/litepali-impl && python -c "from python.tools.document_query import DocumentQueryTool; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add python/tools/document_query.py
git commit -m "feat: add mode parameter to document_query tool (text/visual/auto)"
```

---

## Task 10: Update Tool Prompt

**Files:**
- Modify: `prompts/agent.system.tool.document_query.md`

**Step 1: Add visual mode documentation**

Append to end of file:
```markdown

4 visual document analysis
use mode "visual" for documents with complex layouts charts tables
~~~json
{
    "thoughts": [
        "This PDF has charts and tables, visual mode will help..."
    ],
    "headline": "Analyzing document visually",
    "tool_name": "document_query",
    "tool_args": {
        "document": "file:///path/to/report.pdf",
        "queries": ["What does the revenue chart show?"],
        "mode": "visual"
    }
}
~~~

5 auto mode (both text and visual analysis)
use mode "auto" when unsure which approach works best
returns both text and visual results in separate sections
~~~json
{
    "thoughts": [
        "Not sure if text or visual will work better for this document..."
    ],
    "headline": "Analyzing document with text and visual",
    "tool_name": "document_query",
    "tool_args": {
        "document": "https://example.com/paper.pdf",
        "queries": ["Summarize the methodology section"],
        "mode": "auto"
    }
}
~~~
```

**Step 2: Verify prompt file is valid**

Run: `cat prompts/agent.system.tool.document_query.md | head -80`
Expected: Shows full prompt including new visual mode sections

**Step 3: Commit**

```bash
git add prompts/agent.system.tool.document_query.md
git commit -m "docs: add visual and auto mode examples to document_query prompt"
```

---

## Task 11: Integration Test

**Files:**
- None (verification only)

**Step 1: Verify all imports work together**

Run:
```bash
cd /Users/lazy/agent-zero-dev/.worktrees/litepali-impl && python -c "
from python.helpers.settings import get_default_settings
from python.helpers.visual_document_query import VisualDocumentStore, VisualDocumentQueryHelper, VisualMatch
from python.tools.document_query import DocumentQueryTool

settings = get_default_settings()
print(f'visual_doc_enabled: {settings.get(\"visual_doc_enabled\")}')
print(f'visual_doc_model_name: {settings.get(\"visual_doc_model_name\")}')
print('All imports successful!')
"
```
Expected:
```
visual_doc_enabled: True
visual_doc_model_name: vidore/colpali-v1.2
All imports successful!
```

**Step 2: Create final commit for phase 1**

```bash
git log --oneline -10  # Review commits
```

**Step 3: Tag phase 1 completion**

```bash
git tag -a phase1-complete -m "Phase 1: Core LitePali integration complete"
```

---

## Summary

Phase 1 implements:
- Settings for visual document query configuration
- `VisualDocumentStore` class with lazy-loaded LitePali
- PDF-to-image conversion using existing pdf2image
- Document indexing and visual search
- `VisualDocumentQueryHelper` for tool integration
- Extended `document_query` tool with mode parameter
- Updated tool prompt with visual mode examples

**Next Phase:** Storage persistence, global indexes, index management operations.
