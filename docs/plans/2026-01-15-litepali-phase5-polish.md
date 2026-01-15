# Phase 5: Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add user-facing polish to the LitePali visual document query feature - settings UI, better error messages, progress reporting, and documentation.

**Architecture:** Extend existing infrastructure with UI components following Agent Zero's Alpine.js patterns, enhance error handling with custom exceptions, and improve progress callbacks with stage indicators.

**Tech Stack:** Alpine.js for UI, Python dataclasses for exceptions, existing progress callback infrastructure.

---

## Task 1: Create Settings UI Component

**Files:**
- Create: `webui/components/settings/agent/visual_document.html`

**Step 1: Create the settings component**

Reference the pattern in `webui/components/settings/agent/speech.html` for Alpine.js bindings.

```html
<div class="settings-section">
    <div class="settings-section-title">
        <span class="material-symbols-outlined">image_search</span>
        Visual Document Query
    </div>
    <div class="settings-section-content">
        <!-- Enable toggle -->
        <div class="settings-item">
            <label class="switch">
                <input type="checkbox" x-model="settings.visual_doc_enabled">
                <span class="slider"></span>
            </label>
            <span>Enable visual document query</span>
        </div>

        <div x-show="settings.visual_doc_enabled" x-transition>
            <!-- Execution Mode -->
            <div class="settings-item">
                <label>Execution Mode</label>
                <select x-model="settings.visual_doc_execution_mode">
                    <option value="in_process">In-Process (simple, uses main memory)</option>
                    <option value="subprocess">Subprocess (isolated, better memory)</option>
                    <option value="docker_sidecar">Docker Sidecar (containerized)</option>
                </select>
            </div>

            <!-- Model Name -->
            <div class="settings-item">
                <label>Model</label>
                <select x-model="settings.visual_doc_model_name">
                    <option value="vidore/colpali-v1.2">ColPali v1.2 (recommended)</option>
                    <option value="vidore/colpali">ColPali v1.0</option>
                </select>
            </div>

            <!-- Batch Size -->
            <div class="settings-item">
                <label>Batch Size</label>
                <input type="number" x-model.number="settings.visual_doc_batch_size" min="1" max="64">
                <span class="hint">Images processed per batch (lower = less memory)</span>
            </div>

            <!-- PDF DPI -->
            <div class="settings-item">
                <label>PDF DPI</label>
                <input type="number" x-model.number="settings.visual_doc_pdf_dpi" min="72" max="300">
                <span class="hint">Resolution for PDF conversion (144 recommended)</span>
            </div>

            <!-- Max Pages -->
            <div class="settings-item">
                <label>Max Pages</label>
                <input type="number" x-model.number="settings.visual_doc_max_pages" min="1" max="500">
                <span class="hint">Maximum pages to index per document</span>
            </div>

            <!-- Max File Size -->
            <div class="settings-item">
                <label>Max File Size (MB)</label>
                <input type="number" x-model.number="settings.visual_doc_max_file_size_mb" min="1" max="200">
            </div>

            <!-- Keep Model Loaded (only for in_process) -->
            <div class="settings-item" x-show="settings.visual_doc_execution_mode === 'in_process'">
                <label class="switch">
                    <input type="checkbox" x-model="settings.visual_doc_keep_model_loaded">
                    <span class="slider"></span>
                </label>
                <span>Keep model loaded between requests</span>
                <span class="hint">Uses ~2-3GB RAM but faster subsequent queries</span>
            </div>
        </div>
    </div>
</div>
```

**Step 2: Verify file created**

Run: `ls -la webui/components/settings/agent/visual_document.html`
Expected: File exists

**Step 3: Commit**

```bash
git add webui/components/settings/agent/visual_document.html
git commit -m "feat: add settings UI component for visual document query"
```

---

## Task 2: Add Settings UI to Navigation

**Files:**
- Modify: `webui/components/settings/agent/agent-settings.html`

**Step 1: Find the includes section and add visual_document**

Look for patterns like:
```html
<div hx-get="/components/settings/agent/speech.html" hx-trigger="load"></div>
```

Add after the last agent settings include:
```html
<div hx-get="/components/settings/agent/visual_document.html" hx-trigger="load"></div>
```

**Step 2: Verify the change**

Run: `grep "visual_document" webui/components/settings/agent/agent-settings.html`
Expected: Shows the include line

**Step 3: Commit**

```bash
git add webui/components/settings/agent/agent-settings.html
git commit -m "feat: add visual document settings to agent settings navigation"
```

---

## Task 3: Add Custom Exception Classes

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add exception classes after imports (around line 15)**

```python
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
```

**Step 2: Verify syntax**

Run: `python -m py_compile python/helpers/visual_document_query.py`
Expected: No errors

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add custom exception classes for visual document errors"
```

---

## Task 4: Enhance Error Messages with Context

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Update file size validation error (in index_document method)**

Find the file size check and update error message:

```python
if file_size_mb > max_size_mb:
    raise ResourceLimitError(
        f"File too large ({file_size_mb:.1f}MB exceeds {max_size_mb}MB limit). "
        f"Reduce document size or increase 'visual_doc_max_file_size_mb' setting."
    )
```

**Step 2: Update model loading errors (in _initialize_litepali)**

```python
except ImportError as e:
    raise ModelLoadError(
        "LitePali not installed. Install with: pip install litepali colpali-engine. "
        f"Original error: {e}"
    ) from e
```

**Step 3: Update PDF conversion errors**

Wrap pdf2image calls:
```python
try:
    images = pdf2image.convert_from_path(...)
except Exception as e:
    raise DocumentProcessingError(
        f"Failed to convert PDF to images: {e}. "
        "Ensure poppler-utils is installed (apt-get install poppler-utils)."
    ) from e
```

**Step 4: Commit**

```bash
git commit -am "feat: enhance error messages with actionable context"
```

---

## Task 5: Add Progress Tracker Class

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Add ProgressTracker class after exceptions**

```python
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
```

**Step 2: Commit**

```bash
git commit -am "feat: add ProgressTracker class for stage-based progress reporting"
```

---

## Task 6: Integrate Progress Tracker into Index Operation

**Files:**
- Modify: `python/helpers/visual_document_query.py`

**Step 1: Update index_document method to use ProgressTracker**

At the start of index_document, create tracker:
```python
tracker = ProgressTracker(progress_callback)
```

Replace generic callbacks with staged progress:
```python
# Stage 1: Download/locate document
tracker.start_stage("Locating document", 1, 5)

# Stage 2: Validate file
tracker.start_stage("Validating file", 2, 5)

# Stage 3: Convert PDF
tracker.start_stage("Converting PDF to images", 3, 5)
for i, image in enumerate(images):
    tracker.update(f"Page {i+1}/{len(images)}", int((i+1)/len(images)*100))

# Stage 4: Process with model
tracker.start_stage("Processing through vision model", 4, 5)

# Stage 5: Save index
tracker.start_stage("Saving index", 5, 5)

tracker.complete()
```

**Step 2: Commit**

```bash
git commit -am "feat: integrate ProgressTracker into document indexing"
```

---

## Task 7: Update Documentation in extensibility.md

**Files:**
- Modify: `docs/extensibility.md`

**Step 1: Add Visual Document Query section**

Find a suitable location (after "Projects" section or similar) and add:

```markdown
## Visual Document Query

Agent Zero includes visual document query capabilities for layout-aware document retrieval using the LitePali vision-language model.

### Overview

Visual document query enables searching documents by visual understanding rather than just text extraction. This is particularly useful for:
- Documents with complex layouts (tables, charts, figures)
- Scanned documents where OCR may be imperfect
- Forms and invoices with structured visual information
- Scientific papers with figures and equations

### Execution Modes

| Mode | Description | Best For |
|------|-------------|----------|
| `in_process` | LitePali runs in main process | Simple setups, development |
| `subprocess` | Isolated Python subprocess | Memory isolation, stability |
| `docker_sidecar` | Dedicated Docker container | Containerized deployments |

Configure via `visual_doc_execution_mode` setting. Fallback chain: docker_sidecar → subprocess → in_process.

### Storage

Visual document indexes are stored in two scopes:
- **Project scope**: `.a0proj/visual_docs/` - Document indexes specific to current project
- **Global scope**: `usr/visual_docs/` - Shared indexes across projects

### Configuration

Key settings (in Settings UI under Agent → Visual Document Query):
- `visual_doc_enabled`: Enable/disable the feature
- `visual_doc_model_name`: LitePali model to use
- `visual_doc_execution_mode`: How to run the model
- `visual_doc_batch_size`: Images per batch (affects memory)
- `visual_doc_pdf_dpi`: PDF conversion resolution
- `visual_doc_max_pages`: Page limit per document
- `visual_doc_max_file_size_mb`: File size limit

### Usage

Use the `document_query` tool with `mode` parameter:
- `mode: "text"` - Traditional text extraction (default)
- `mode: "visual"` - Visual understanding with LitePali
- `mode: "auto"` - Both text and visual results

### Resource Requirements

- **Memory**: ~2-3GB for model loading (in_process mode)
- **Storage**: ~10-50MB per indexed document (images + embeddings)
- **GPU**: Optional but recommended (CUDA, MPS supported)
```

**Step 2: Commit**

```bash
git add docs/extensibility.md
git commit -m "docs: add Visual Document Query section to extensibility.md"
```

---

## Task 8: Run Integration Test

**Step 1: Verify all imports work**

Run: `python -c "from python.helpers.visual_document_query import ProgressTracker, VisualDocumentError; print('OK')"`
Expected: "OK"

**Step 2: Verify settings UI file exists**

Run: `ls webui/components/settings/agent/visual_document.html`
Expected: File exists

**Step 3: Verify documentation updated**

Run: `grep "Visual Document Query" docs/extensibility.md`
Expected: Shows section header

---

## Summary

Phase 5 adds user-facing polish:

1. **Settings UI** - Visual configuration for all visual document settings
2. **Custom Exceptions** - Typed exceptions with actionable error messages
3. **Progress Tracking** - Stage-based progress reporting
4. **Documentation** - Comprehensive guide in extensibility.md

After implementation, users can:
- Configure visual document query from the web UI
- See clear progress during long indexing operations
- Get helpful error messages when things go wrong
- Reference documentation for advanced configuration
