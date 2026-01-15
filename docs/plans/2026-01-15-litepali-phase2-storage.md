# LitePali Phase 2: Storage & Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add persistent index registry, scope resolution, and management operations (list/delete/reindex) to visual document query.

**Architecture:** Extend `VisualDocumentStore` with an `IndexRegistry` class that maintains a central JSON file tracking all indexed documents. Add scope resolution to search project indexes first, then fall back to global. Expose management operations through the existing `document_query` tool via a `method` parameter.

**Tech Stack:** Python, JSON for registry persistence, existing LitePali infrastructure from Phase 1.

---

## Task 1: Create IndexRegistry Class

**Files:**
- Modify: `python/helpers/visual_document_query.py:1-25` (add imports and new class)

**Step 1: Add IndexRegistry dataclass and class skeleton**

Add after the imports, before `VisualMatch`:

```python
from dataclasses import dataclass, field, asdict
from typing import Dict

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
            with open(self.registry_path, 'r') as f:
                data = json.load(f)
                self._entries = {
                    uri: IndexEntry.from_dict(entry)
                    for uri, entry in data.items()
                }
        self._loaded = True

    def _save(self) -> None:
        """Save registry to JSON file."""
        import json
        os.makedirs(self.storage_path, exist_ok=True)
        with open(self.registry_path, 'w') as f:
            json.dump(
                {uri: entry.to_dict() for uri, entry in self._entries.items()},
                f,
                indent=2
            )

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
```

**Step 2: Verify syntax**

Run: `python -m py_compile python/helpers/visual_document_query.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add IndexRegistry class for tracking indexed documents"
```

---

## Task 2: Integrate IndexRegistry into VisualDocumentStore

**Files:**
- Modify: `python/helpers/visual_document_query.py` (VisualDocumentStore class)

**Step 1: Add registry to VisualDocumentStore.__init__**

In `VisualDocumentStore.__init__`, after `self._index_loaded = False`, add:

```python
        self.registry = IndexRegistry(self.storage_path)
```

**Step 2: Update index_document to use registry**

In `index_document` method, replace the metadata saving section (the part that creates metadata dict and saves to metadata.json) with code that also registers in the registry:

Find this section (around line 245-255):
```python
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
```

Replace with:
```python
            # Save metadata and register
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
```

**Step 3: Update document existence check to use registry**

In `index_document`, replace:
```python
        # Check if already indexed
        index_dir = self.storage_path / "indexes" / doc_hash
        if (index_dir / "metadata.json").exists():
            callback(f"Document already indexed: {document_uri}")
            return True
```

With:
```python
        # Check if already indexed (registry is source of truth)
        index_dir = self.storage_path / "indexes" / doc_hash
        if self.registry.exists(uri_normalized):
            callback(f"Document already indexed: {document_uri}")
            return True
```

**Step 4: Verify syntax**

Run: `python -m py_compile python/helpers/visual_document_query.py`
Expected: No output (success)

**Step 5: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: integrate IndexRegistry into VisualDocumentStore"
```

---

## Task 3: Add Management Methods to VisualDocumentStore

**Files:**
- Modify: `python/helpers/visual_document_query.py` (add methods to VisualDocumentStore)

**Step 1: Add delete_document method**

Add after the `search` method in `VisualDocumentStore`:

```python
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
```

**Step 2: Add list_documents method**

Add after `delete_document`:

```python
    def list_documents(self) -> List[IndexEntry]:
        """
        List all indexed documents.

        Returns:
            List of IndexEntry objects
        """
        return self.registry.list_all()
```

**Step 3: Add reindex_document method**

Add after `list_documents`:

```python
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
```

**Step 4: Add get_disk_usage method**

Add after `reindex_document`:

```python
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
```

**Step 5: Verify syntax**

Run: `python -m py_compile python/helpers/visual_document_query.py`
Expected: No output (success)

**Step 6: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add delete, list, reindex, and disk usage methods"
```

---

## Task 4: Add Scope Resolution (Project → Global Fallback)

**Files:**
- Modify: `python/helpers/visual_document_query.py` (VisualDocumentStore and VisualDocumentQueryHelper)

**Step 1: Add class method to get both stores**

Add as a static method in `VisualDocumentStore`:

```python
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
```

**Step 2: Add find_document method with scope resolution**

Add after `get_stores`:

```python
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
```

**Step 3: Update VisualDocumentQueryHelper to support scope parameter**

In `VisualDocumentQueryHelper.__init__`, change:
```python
        self.store = VisualDocumentStore(agent, scope="project")
```

To:
```python
        self.scope = "project"  # Default scope for new indexes
        self._project_store = VisualDocumentStore(agent, scope="project")
        self._global_store = VisualDocumentStore(agent, scope="global")
```

**Step 4: Add method to get store for document with fallback**

Add after `__init__` in `VisualDocumentQueryHelper`:

```python
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
```

**Step 5: Update visual_document_qa to use scope resolution**

In `visual_document_qa`, change the indexing loop:
```python
        # Index all documents
        for uri in document_uris:
            await self.store.index_document(uri, self.progress_callback)
            await self.agent.handle_intervention()
```

To:
```python
        # Index all documents (use existing store or project store for new)
        for uri in document_uris:
            store = self._get_store_for_document(uri)
            await store.index_document(uri, self.progress_callback)
            await self.agent.handle_intervention()
```

**Step 6: Update search to check both scopes**

In `visual_document_qa`, change the search loop to search both stores:
```python
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
```

**Step 7: Verify syntax**

Run: `python -m py_compile python/helpers/visual_document_query.py`
Expected: No output (success)

**Step 8: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add scope resolution with project→global fallback"
```

---

## Task 5: Add Management Methods to VisualDocumentQueryHelper

**Files:**
- Modify: `python/helpers/visual_document_query.py` (VisualDocumentQueryHelper class)

**Step 1: Add list_indexed_documents method**

Add to `VisualDocumentQueryHelper`:

```python
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
```

**Step 2: Add delete_indexed_document method**

Add after `list_indexed_documents`:

```python
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
```

**Step 3: Add reindex_document method**

Add after `delete_indexed_document`:

```python
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

        success = await target_store.reindex_document(document_uri, self.progress_callback)
        if success:
            return f"Re-indexed: {document_uri} (in {target_store.scope} scope)"
        return f"Failed to re-index: {document_uri}"
```

**Step 4: Verify syntax**

Run: `python -m py_compile python/helpers/visual_document_query.py`
Expected: No output (success)

**Step 5: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add list, delete, reindex methods to helper"
```

---

## Task 6: Add Method Parameter to document_query Tool

**Files:**
- Modify: `python/tools/document_query.py`

**Step 1: Add method parameter handling**

In `execute` method, after mode handling and before the try block, add:

```python
        # Get method parameter for management operations
        method = kwargs.get("method", "query")
        if method not in ("query", "list", "delete", "reindex"):
            method = "query"

        # Handle management operations (visual mode only)
        if method != "query":
            if mode == "text":
                return Response(
                    message="Error: Management methods (list/delete/reindex) only work with mode='visual'",
                    break_loop=False
                )

            try:
                from python.helpers.visual_document_query import VisualDocumentQueryHelper

                progress = []
                def progress_callback(msg):
                    progress.append(msg)
                    self.log.update(progress="\n".join(progress))

                visual_helper = VisualDocumentQueryHelper(self.agent, progress_callback)

                if method == "list":
                    scope = kwargs.get("scope")  # Optional: "project", "global", or None
                    result = visual_helper.list_indexed_documents(scope)
                    return Response(message=result, break_loop=False)

                elif method == "delete":
                    if not document_uris:
                        return Response(message="Error: document required for delete", break_loop=False)
                    results = []
                    for uri in document_uris:
                        result = await visual_helper.delete_indexed_document(uri)
                        results.append(result)
                    return Response(message="\n".join(results), break_loop=False)

                elif method == "reindex":
                    if not document_uris:
                        return Response(message="Error: document required for reindex", break_loop=False)
                    scope = kwargs.get("scope")
                    results = []
                    for uri in document_uris:
                        result = await visual_helper.reindex_indexed_document(uri, scope)
                        results.append(result)
                    return Response(message="\n".join(results), break_loop=False)

            except ImportError:
                return Response(
                    message="Error: Visual mode requires litepali. Install with: pip install litepali",
                    break_loop=False
                )
```

**Step 2: Verify syntax**

Run: `python -m py_compile python/tools/document_query.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add python/tools/document_query.py
git commit -m "feat: add method parameter for list/delete/reindex operations"
```

---

## Task 7: Update Tool Prompt with Management Examples

**Files:**
- Modify: `prompts/agent.system.tool.document_query.md`

**Step 1: Add management examples**

Append to the file:

```markdown

### Visual Index Management

6 list indexed documents
~~~json
{
    "thoughts": [
        "I need to see what documents are already indexed for visual search..."
    ],
    "headline": "Listing indexed documents",
    "tool_name": "document_query",
    "tool_args": {
        "mode": "visual",
        "method": "list"
    }
}
~~~

7 delete document from visual index
~~~json
{
    "thoughts": [
        "This document is outdated, I should remove it from the visual index..."
    ],
    "headline": "Removing document from index",
    "tool_name": "document_query",
    "tool_args": {
        "document": "file:///path/to/old-report.pdf",
        "mode": "visual",
        "method": "delete"
    }
}
~~~

8 reindex document (force refresh)
~~~json
{
    "thoughts": [
        "The document has been updated, I need to refresh the visual index..."
    ],
    "headline": "Re-indexing updated document",
    "tool_name": "document_query",
    "tool_args": {
        "document": "file:///path/to/updated-report.pdf",
        "mode": "visual",
        "method": "reindex"
    }
}
~~~

9 index document to global scope (shared across projects)
~~~json
{
    "thoughts": [
        "This reference document should be available to all projects..."
    ],
    "headline": "Indexing to global scope",
    "tool_name": "document_query",
    "tool_args": {
        "document": "https://example.com/reference-guide.pdf",
        "mode": "visual",
        "method": "reindex",
        "scope": "global"
    }
}
~~~
```

**Step 2: Commit**

```bash
git add prompts/agent.system.tool.document_query.md
git commit -m "docs: add visual index management examples to tool prompt"
```

---

## Task 8: Add Cleanup Utility for Orphaned Indexes

**Files:**
- Modify: `python/helpers/visual_document_query.py` (VisualDocumentStore class)

**Step 1: Add cleanup_orphaned_indexes method**

Add to `VisualDocumentStore` after `get_disk_usage`:

```python
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
                freed_bytes += dir_size

                callback(f"Removing orphaned index: {doc_dir.name}")
                shutil.rmtree(doc_dir)
                removed_count += 1

        result = {
            "removed_count": removed_count,
            "freed_mb": freed_bytes / (1024 * 1024)
        }

        callback(f"Cleanup complete: removed {removed_count} orphans, freed {result['freed_mb']:.1f}MB")
        return result
```

**Step 2: Add cleanup method to VisualDocumentQueryHelper**

Add to `VisualDocumentQueryHelper`:

```python
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
```

**Step 3: Verify syntax**

Run: `python -m py_compile python/helpers/visual_document_query.py`
Expected: No output (success)

**Step 4: Commit**

```bash
git add python/helpers/visual_document_query.py
git commit -m "feat: add cleanup utility for orphaned indexes"
```

---

## Task 9: Final Integration Test

**Files:**
- None (verification only)

**Step 1: Verify all imports work**

Run:
```bash
python -c "
from python.helpers.visual_document_query import (
    VisualMatch,
    IndexEntry,
    IndexRegistry,
    VisualDocumentStore,
    VisualDocumentQueryHelper
)
print('All imports OK')

# Verify new methods exist
assert hasattr(VisualDocumentStore, 'delete_document')
assert hasattr(VisualDocumentStore, 'list_documents')
assert hasattr(VisualDocumentStore, 'reindex_document')
assert hasattr(VisualDocumentStore, 'get_disk_usage')
assert hasattr(VisualDocumentStore, 'cleanup_orphaned_indexes')
assert hasattr(VisualDocumentStore, 'find_document')
assert hasattr(VisualDocumentStore, 'get_stores')
assert hasattr(VisualDocumentQueryHelper, 'list_indexed_documents')
assert hasattr(VisualDocumentQueryHelper, 'delete_indexed_document')
assert hasattr(VisualDocumentQueryHelper, 'reindex_indexed_document')
assert hasattr(VisualDocumentQueryHelper, 'cleanup_indexes')
print('All methods present')
"
```

Expected: "All imports OK" and "All methods present"

**Step 2: Verify tool imports**

Run:
```bash
python -c "from python.tools.document_query import DocumentQueryTool; print('Tool import OK')"
```

Expected: "Tool import OK"

**Step 3: Create completion tag**

```bash
git tag phase2-complete
git log --oneline -10
```

---

## Summary

Phase 2 adds:
- `IndexRegistry` class for centralized document tracking
- `IndexEntry` dataclass for registry entries
- Scope resolution (project → global fallback)
- Management methods: `delete_document`, `list_documents`, `reindex_document`
- Disk usage tracking: `get_disk_usage`
- Cleanup utility: `cleanup_orphaned_indexes`
- Tool integration via `method` parameter
- Updated prompts with management examples

**Files Modified:**
- `python/helpers/visual_document_query.py` - Core changes
- `python/tools/document_query.py` - Method parameter
- `prompts/agent.system.tool.document_query.md` - Examples

**Total Tasks:** 9
**Estimated Commits:** 8
