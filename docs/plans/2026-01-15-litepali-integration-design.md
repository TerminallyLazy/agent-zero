# LitePali Integration Design

> Visual document retrieval for Agent Zero via unified `document_query` tool

**Date:** 2026-01-15
**Status:** Draft
**Branch:** `feat-implement-LITEPALI-visual-doc-search`

---

## Overview

Integrate LitePali (a lightweight vision-language model for document retrieval) into Agent Zero's existing `document_query` tool. This enables hybrid text+visual document understanding through a unified interface with configurable execution modes.

### Goals

- Add visual document retrieval capabilities for layout-aware search
- Maintain backward compatibility with existing text-based document queries
- Support diverse deployments (local, Docker, resource-constrained environments)
- Provide transparent results that let the agent reason about text vs. visual matches

### Non-Goals

- Replacing the existing text pipeline (complementary, not replacement)
- Automatic result fusion/ranking (agent decides based on context)
- Real-time video or streaming document processing

---

## Architecture

### Unified Tool Interface

Enhance `document_query` with a `mode` parameter:

```python
document_query(
    document: str | list[str],
    queries: list[str],
    mode: "text" | "visual" | "auto"  # Defaults to "text" for backward compat
)
```

| Mode | Behavior |
|------|----------|
| `text` | Existing text extraction + semantic search (default) |
| `visual` | LitePali vision model for layout-aware retrieval |
| `auto` | Run both pipelines, return separate labeled sections |

### Component Structure

```
python/helpers/
├── document_query.py           # Existing - add mode routing
├── visual_document_query.py    # NEW - LitePali integration & VisualDocumentStore
└── visual_document_service.py  # NEW - subprocess/sidecar management

python/tools/
└── document_query.py           # Existing - add mode parameter handling
```

### Data Flow

1. Tool receives request with `mode` parameter
2. Routes to text pipeline, visual pipeline, or both (auto)
3. Each pipeline returns results independently
4. Results returned with clear section labels
5. Agent reasons about which results to use for the task

---

## Visual Pipeline Implementation

### VisualDocumentStore

```python
class VisualDocumentStore:
    """Manages LitePali indexes - global and project-scoped"""

    GLOBAL_PATH = "/a0/usr/visual_docs/"
    PROJECT_PATH = ".a0proj/visual_docs/"

    def __init__(self, agent: Agent, scope: Literal["global", "project"]):
        self.scope = scope
        self.storage_path = self._resolve_path(agent)
        self.litepali: LitePali | None = None  # Lazy loaded

    async def index_document(self, uri: str, images: list[Path]) -> list[str]:
        """Index document images, return chunk IDs"""

    async def search(self, query: str, limit: int = 10) -> list[VisualMatch]:
        """Search indexed documents by visual similarity"""

    async def document_exists(self, uri: str) -> bool:
        """Check if document is already indexed"""

    def save_index(self) -> None:
        """Persist index to storage"""

    def load_index(self) -> None:
        """Load index from storage"""
```

### VisualMatch Result Type

```python
@dataclass
class VisualMatch:
    document_uri: str
    page_number: int
    score: float
    image_path: Path      # Reference to cached page image
    snippet: str          # OCR text from matched region (if available)
```

### PDF-to-Image Pipeline

- Reuse existing `pdf2image` dependency from `requirements.txt`
- Store converted images alongside embeddings for caching
- Configurable DPI (default 300) via settings
- Page limit enforcement (default 100 pages max)

---

## Resource Management

### Settings Configuration

Add to `settings.py`:

```python
"visual_document_query": {
    "enabled": True,
    "model_name": "vidore/colpali-v1.2",
    "execution_mode": "in_process",  # "in_process" | "subprocess" | "docker_sidecar"
    "keep_model_loaded": True,       # Only for in_process mode
    "batch_size": 32,
    "pdf_dpi": 300,
    "max_pages": 100,
    "max_file_size_mb": 50
}
```

### Execution Modes

#### In-Process Mode
- LitePali loaded directly in Agent Zero process
- `keep_model_loaded: true` keeps ~2-3GB model in memory
- `keep_model_loaded: false` loads/unloads per request
- Best for: Dedicated machines with sufficient RAM

#### Subprocess Mode
- LitePali runs in isolated Python subprocess
- Communication via JSON lines over stdin/stdout
- Managed by `VisualDocumentService` class
- Best for: Local development, memory isolation

```python
class VisualDocumentService:
    """Manages LitePali in isolated subprocess"""

    def __init__(self, settings: dict):
        self.process: subprocess.Popen | None = None

    async def start(self) -> None:
        """Launch python -m python.helpers.visual_document_worker"""

    async def request(self, action: str, payload: dict) -> dict:
        """Send JSON request, await JSON response"""

    async def shutdown(self) -> None:
        """Graceful termination"""
```

#### Docker Sidecar Mode
- Standalone container running visual service
- Dockerfile in `docker/visual_document_service/`
- Shares `/a0/usr/` volume for index access
- Auto-spawned via Agent Zero's Docker helpers
- Best for: Containerized deployments, resource isolation

### Fallback Chain

If configured mode fails, gracefully degrade:

```
docker_sidecar → subprocess → in_process → error with message
```

---

## Storage & Index Management

### Directory Structure

```
# Global indexes (shared across projects)
/a0/usr/visual_docs/
├── indexes/
│   └── {document_hash}/
│       ├── embeddings.safetensors
│       ├── metadata.json
│       └── images/
│           ├── page_001.png
│           ├── page_002.png
│           └── ...
└── index_registry.json

# Project-scoped indexes
/a0/usr/projects/{project_name}/
└── .a0proj/visual_docs/
    ├── indexes/
    │   └── {document_hash}/...
    └── index_registry.json
```

### Index Registry

```json
{
  "https://example.com/report.pdf": {
    "hash": "a1b2c3d4e5f6",
    "indexed_at": "2026-01-15T10:30:00Z",
    "page_count": 12,
    "file_size_mb": 2.4,
    "scope": "global"
  },
  "file:///project/local-doc.pdf": {
    "hash": "b2c3d4e5f6a1",
    "indexed_at": "2026-01-15T11:00:00Z",
    "page_count": 5,
    "file_size_mb": 0.8,
    "scope": "project"
  }
}
```

### Scope Resolution

1. Check project index first (more specific)
2. Fall back to global index
3. When indexing: default to project scope
4. Use `scope: "global"` parameter explicitly for shared documents

### Management Operations

Extend `document_query` tool methods:
- `method: "delete"` - Remove document from visual index
- `method: "list"` - Show indexed documents with scope
- `method: "reindex"` - Force re-processing of document

---

## Tool Prompt Updates

Add to `prompts/agent.system.tool.document_query.md`:

```markdown
### document_query (visual mode)
set mode to "visual" for documents with complex layouts charts tables
set mode to "auto" to get both text and visual results
visual mode uses AI vision models to understand document structure
useful for scanned documents forms invoices scientific papers with figures

4 visual document analysis
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

5 auto mode (both pipelines)
~~~json
{
    "thoughts": [
        "Not sure if text or visual will work better, trying both..."
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

### Response Format (Auto Mode)

```
## Text Results

[Existing text-based semantic search results]

## Visual Results

**Page 3** (score: 0.87)
[Description of matched visual content]
Image: .a0proj/visual_docs/indexes/abc123/images/page_003.png

**Page 7** (score: 0.72)
[Description of matched visual content]

---
Note: Both text and visual analysis provided. Visual results may capture
layout-dependent information (tables, charts, figures) that text extraction missed.
```

---

## Dependencies

Add to `requirements.txt`:

```txt
litepali>=0.0.5
colpali-engine>=0.3.0,<0.4.0
safetensors>=0.4.0
```

Note: `pdf2image` already present in requirements.

---

## Implementation Phases

### Phase 1: Core Integration
- [ ] Create `visual_document_query.py` helper with `VisualDocumentStore`
- [ ] Implement in-process execution mode only
- [ ] Modify `document_query.py` tool to accept `mode` parameter
- [ ] Add visual mode examples to tool prompt
- [ ] Basic error handling and progress reporting

### Phase 2: Storage & Persistence
- [ ] Implement global + project-scoped index management
- [ ] Create index registry with document tracking
- [ ] Image caching and cleanup utilities
- [ ] Add `delete`, `list`, `reindex` methods

### Phase 3: Process Isolation
- [ ] Implement subprocess mode with JSON pipe communication
- [ ] Create `visual_document_worker.py` standalone script
- [ ] Add fallback chain logic
- [ ] Settings validation for execution modes

### Phase 4: Docker Sidecar
- [ ] Create `docker/visual_document_service/Dockerfile`
- [ ] Integrate with Agent Zero's Docker helpers
- [ ] Volume mounting for shared indexes
- [ ] Health checks and auto-restart

### Phase 5: Polish
- [ ] Settings UI integration for visual query options
- [ ] Comprehensive error messages
- [ ] Progress reporting with stage indicators
- [ ] Documentation updates in `docs/extensibility.md`

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Separate vs. unified tool | Unified with `mode` | Simpler agent prompts, backward compatible |
| Result fusion strategy | Separate sections | Transparent to agent, avoids mixing apples/oranges |
| Storage scope | Global + project | Flexibility for shared libraries and isolation |
| Process isolation | Subprocess + Docker sidecar | Covers local dev and containerized deployments |
| Model loading | Configurable | Different hardware has different constraints |

---

## Security Considerations

- Validate and sanitize file paths using Agent Zero's file helpers
- Prevent directory traversal in document URIs
- Validate URLs before downloading remote documents
- Project-scoped storage maintains security isolation
- Size limits prevent resource exhaustion attacks

---

## Open Questions

1. Should visual results include base64-encoded thumbnail previews in the response?
2. Should we support incremental indexing (add pages to existing index)?
3. Worth adding a "visual-only" confidence threshold that skips text pipeline?

---

## References

- [LitePali Documentation](https://github.com/vidore/litepali)
- [ColPali Paper](https://arxiv.org/abs/2407.01449)
- Agent Zero `document_query.py` tool and helper
- Agent Zero extensibility patterns in `docs/extensibility.md`
