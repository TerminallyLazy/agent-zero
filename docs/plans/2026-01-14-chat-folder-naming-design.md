# Chat Folder Naming Design

**Date:** 2026-01-14
**Status:** Design Complete
**Author:** Agent Zero Enhancement

## Executive Summary

This design implements human-readable folder naming for Agent Zero chats, replacing random alphanumeric IDs (`tmp/chats/eeFXa0TR/`) with descriptive, slug-based names (`tmp/chats/20240115_142530_database-setup_eeFX/`). The solution includes automatic migration, real-time folder renaming on title changes, and enhanced message file naming with contextual information.

## Problem Statement

The current chat storage system has several discoverability issues:

1. **Poor Discoverability**: Random IDs (`eeFXa0TR/`) make it impossible to identify chats by browsing the file system
2. **No Context in File Names**: Numbered files (`1.txt`, `2.txt`) don't indicate what they contain
3. **Disconnect Between Title and Storage**: AI-generated titles exist but aren't reflected in folder structure
4. **Difficult Search**: Users can't easily grep or search for specific conversations

## Goals

1. ✅ Human-readable folder names that reflect chat content
2. ✅ Descriptive message file names with tool context
3. ✅ Backward compatibility with existing chats
4. ✅ Gradual, safe migration path
5. ✅ No performance degradation
6. ✅ Seamless integration with Agent Zero architecture

## Design Overview

### Core Architecture

**Migration-Based Approach (C)**: New chats use slug-based folders immediately, old chats migrate on first run. This follows Agent Zero's existing migration pattern (`_convert_v080_chats`) and provides a safe transition.

**Dual-Format Support**: The system supports both legacy and new formats during transition:
- **Legacy format**: `tmp/chats/eeFXa0TR/`
- **New format**: `tmp/chats/20240115_142530_database-setup_eeFX/`

### Folder Naming Format

```
tmp/chats/{timestamp}_{slug}_{short_id}/
```

**Components:**
- `{timestamp}`: `YYYYMMDD_HHMMSS` for chronological sorting
- `{slug}`: Sanitized title (lowercase, alphanumeric + hyphens, max 30 chars)
- `{short_id}`: Last 4 chars of original 8-char ID for uniqueness

**Examples:**
```
tmp/chats/20240115_142530_database-setup_eeFX/
tmp/chats/20240115_150122_api-integration_kL9m/
tmp/chats/20240115_163045_bug-fixes_pQr2/
```

### Message File Naming Format

```
messages/{timestamp}_{seq}_{tool_name}_{context}.txt
```

**Examples:**
```
20240115_142530_001_code_python_pandas_analysis.txt
20240115_142535_002_code_bash_install_packages.txt
20240115_142540_003_knowledge_search_database_setup.txt
20240115_143022_004_memory_save_api_credentials.txt
20240115_143045_005_subordinate_researcher_market.txt
```

## Architecture Changes

### Modified Files

1. **`python/helpers/persist_chat.py`** - Core chat persistence logic
2. **`python/extensions/monologue_start/_60_rename_chat.py`** - Handle folder rename on title change
3. **`python/extensions/hist_add_tool_result/_90_save_tool_call_file.py`** - Enhanced message file naming

### New Files

4. **`python/helpers/chat_folder_utils.py`** - Slug generation and folder name utilities

## Detailed Design

### 1. Slug Generation and Folder Utilities

**New module: `python/helpers/chat_folder_utils.py`**

```python
import re
import os
from datetime import datetime
from typing import Tuple

def generate_slug(title: str, max_length: int = 30) -> str:
    """
    Generate a URL-safe slug from a chat title.

    Examples:
        "Database Setup" -> "database-setup"
        "API Integration (v2)" -> "api-integration-v2"
        "Bug: User can't login!" -> "bug-user-cant-login"
    """
    # Convert to lowercase
    slug = title.lower()

    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)

    # Remove non-alphanumeric except hyphens
    slug = re.sub(r'[^a-z0-9\-]', '', slug)

    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Trim hyphens from start/end
    slug = slug.strip('-')

    # Truncate to max length at word boundary if possible
    if len(slug) > max_length:
        slug = slug[:max_length]
        # Try to cut at last hyphen to avoid partial words
        last_hyphen = slug.rfind('-')
        if last_hyphen > max_length // 2:
            slug = slug[:last_hyphen]

    # Fallback if slug is empty
    if not slug:
        slug = "chat"

    return slug

def create_folder_name(context_id: str, title: str = None, created_at: float = None) -> str:
    """
    Create folder name in new format: {timestamp}_{slug}_{short_id}

    Args:
        context_id: The context ID (e.g., "eeFXa0TR")
        title: Chat title (optional, uses "chat" if not provided)
        created_at: Unix timestamp (optional, uses current time if not provided)

    Returns:
        Folder name like "20240115_142530_database-setup_eeFX"
    """
    # Generate timestamp
    if created_at is None:
        created_at = datetime.now().timestamp()

    dt = datetime.fromtimestamp(created_at)
    timestamp = dt.strftime("%Y%m%d_%H%M%S")

    # Generate slug
    slug = generate_slug(title) if title else "chat"

    # Get short ID (last 4 chars)
    short_id = context_id[-4:] if len(context_id) >= 4 else context_id

    return f"{timestamp}_{slug}_{short_id}"

def parse_folder_name(folder_name: str) -> Tuple[bool, str]:
    """
    Parse folder name to determine if it's new format and extract context ID.

    Returns:
        (is_new_format, context_id)

    Examples:
        "20240115_142530_database-setup_eeFX" -> (True, None)
        "eeFXa0TR" -> (False, "eeFXa0TR")
    """
    # New format pattern: YYYYMMDD_HHMMSS_slug_XXXX
    new_format_pattern = r'^\d{8}_\d{6}_[a-z0-9\-]+_([a-zA-Z0-9]{4})$'
    match = re.match(new_format_pattern, folder_name)

    if match:
        # New format - we only have the short ID
        # The full context ID must be stored in chat.json
        return (True, None)
    else:
        # Legacy format - folder name IS the context ID
        return (False, folder_name)

def is_legacy_folder(folder_name: str) -> bool:
    """Check if folder uses legacy naming (random ID only)."""
    is_new, _ = parse_folder_name(folder_name)
    return not is_new
```

### 2. Migration Strategy

**Added to `python/helpers/persist_chat.py`:**

```python
def _migrate_to_slug_folders():
    """
    Migrate legacy chat folders to new slug-based naming.
    Only runs once, similar to _convert_v080_chats().
    """
    # Check if migration already completed
    migration_marker = files.get_abs_path(CHATS_FOLDER, ".migration_slug_complete")
    if os.path.exists(migration_marker):
        return  # Already migrated

    print("Starting chat folder migration to slug-based names...")

    folders = files.list_files(CHATS_FOLDER, "*")
    migrated_count = 0

    for folder_name in folders:
        # Skip migration marker and other non-folder items
        if folder_name.startswith("."):
            continue

        # Check if already new format
        if not chat_folder_utils.is_legacy_folder(folder_name):
            continue

        old_path = files.get_abs_path(CHATS_FOLDER, folder_name)

        # Skip if not a directory
        if not os.path.isdir(old_path):
            continue

        try:
            # Read chat.json to get title and created_at
            chat_file = os.path.join(old_path, CHAT_FILE_NAME)
            if not os.path.exists(chat_file):
                continue

            js = files.read_file(chat_file)
            data = json.loads(js)

            context_id = data.get("id", folder_name)
            title = data.get("name", "chat")
            created_at = data.get("created_at", None)

            # Generate new folder name
            new_folder_name = chat_folder_utils.create_folder_name(
                context_id, title, created_at
            )
            new_path = files.get_abs_path(CHATS_FOLDER, new_folder_name)

            # Rename folder
            files.move_file(old_path, new_path)
            migrated_count += 1

            print(f"Migrated: {folder_name} -> {new_folder_name}")

        except Exception as e:
            print(f"Error migrating {folder_name}: {e}")
            # Continue with other folders

    # Create migration marker
    with open(migration_marker, 'w') as f:
        f.write(f"Migration completed at {datetime.now().isoformat()}\n")
        f.write(f"Migrated {migrated_count} chat folders\n")

    print(f"Migration complete. {migrated_count} folders migrated.")
```

### 3. Context ID Mapping Cache

**Added to `python/helpers/persist_chat.py`:**

```python
# Module-level cache
_context_folder_cache = {}
_cache_initialized = False

def _initialize_folder_cache():
    """
    Build cache of context_id -> folder_name mappings.
    Called once at startup.
    """
    global _context_folder_cache, _cache_initialized

    if _cache_initialized:
        return

    _context_folder_cache.clear()
    folders = files.list_files(CHATS_FOLDER, "*")

    for folder_name in folders:
        if folder_name.startswith("."):
            continue

        folder_path = files.get_abs_path(CHATS_FOLDER, folder_name)
        if not os.path.isdir(folder_path):
            continue

        is_new_format, _ = chat_folder_utils.parse_folder_name(folder_name)

        if is_new_format:
            # Read chat.json to get actual context ID
            chat_file = os.path.join(folder_path, CHAT_FILE_NAME)
            try:
                if os.path.exists(chat_file):
                    js = files.read_file(chat_file)
                    data = json.loads(js)
                    context_id = data.get("id")
                    if context_id:
                        _context_folder_cache[context_id] = folder_name
            except Exception as e:
                print(f"Error reading {chat_file}: {e}")
        else:
            # Legacy format - folder name IS the context ID
            _context_folder_cache[folder_name] = folder_name

    _cache_initialized = True
    print(f"Initialized folder cache with {len(_context_folder_cache)} chats")

def _update_folder_cache(context_id: str, folder_name: str):
    """Update cache when folder is created or renamed."""
    global _context_folder_cache
    _context_folder_cache[context_id] = folder_name

def _remove_from_folder_cache(context_id: str):
    """Remove from cache when chat is deleted."""
    global _context_folder_cache
    _context_folder_cache.pop(context_id, None)
```

**Modified `get_chat_folder_path()`:**

```python
def get_chat_folder_path(ctxid: str) -> str:
    """
    Get the folder path for a context by ID.
    Uses cache for fast O(1) lookup.
    """
    # Ensure cache is initialized
    if not _cache_initialized:
        _initialize_folder_cache()

    # Check cache first
    folder_name = _context_folder_cache.get(ctxid)
    if folder_name:
        return files.get_abs_path(CHATS_FOLDER, folder_name)

    # Not in cache - might be a new chat
    return files.get_abs_path(CHATS_FOLDER, ctxid)
```

**Modified `load_tmp_chats()`:**

```python
def load_tmp_chats():
    """Load all contexts from the chats folder"""
    _convert_v080_chats()  # Existing migration
    _migrate_to_slug_folders()  # NEW: Slug migration
    _initialize_folder_cache()  # NEW: Build cache

    # Load chat.json files
    ctxids = []
    for context_id, folder_name in _context_folder_cache.items():
        chat_file = os.path.join(
            files.get_abs_path(CHATS_FOLDER, folder_name),
            CHAT_FILE_NAME
        )

        try:
            js = files.read_file(chat_file)
            data = json.loads(js)
            ctx = _deserialize_context(data)
            ctxids.append(ctx.id)
        except Exception as e:
            print(f"Error loading chat {chat_file}: {e}")

    return ctxids
```

### 4. Real-Time Folder Renaming

**Modified `python/extensions/monologue_start/_60_rename_chat.py`:**

```python
async def change_name(self):
    try:
        # Existing title generation code...
        history_text = self.agent.history.output_text()
        ctx_length = min(
            int(self.agent.config.utility_model.ctx_length * 0.7), 5000
        )
        history_text = tokens.trim_to_tokens(history_text, ctx_length, "start")

        system = self.agent.read_prompt("fw.rename_chat.sys.md")
        current_name = self.agent.context.name
        message = self.agent.read_prompt(
            "fw.rename_chat.msg.md", current_name=current_name, history=history_text
        )

        new_name = await self.agent.call_utility_model(
            system=system, message=message, background=True
        )

        if new_name:
            # Trim name to max length if needed
            if len(new_name) > 40:
                new_name = new_name[:40] + "..."

            # Store old folder path before rename
            old_folder = persist_chat.get_chat_folder_path(self.agent.context.id)
            old_folder_name = os.path.basename(old_folder)

            # Update context name
            self.agent.context.name = new_name

            # Handle folder renaming
            await self._rename_folder_if_needed(old_folder, old_folder_name, new_name)

            # Save updated context
            persist_chat.save_tmp_chat(self.agent.context)
    except Exception as e:
        print(f"Error renaming chat: {e}")

async def _rename_folder_if_needed(self, old_folder: str, old_folder_name: str, new_title: str):
    """
    Rename the chat folder if title changed.
    - New format folders: rename with updated slug
    - Legacy format folders: migrate to new format
    """
    try:
        is_legacy = chat_folder_utils.is_legacy_folder(old_folder_name)

        # Generate new folder name with updated title
        new_folder_name = chat_folder_utils.create_folder_name(
            context_id=self.agent.context.id,
            title=new_title,
            created_at=self.agent.context.created_at
        )

        # Only rename if different
        if new_folder_name != old_folder_name:
            new_folder = os.path.join(os.path.dirname(old_folder), new_folder_name)

            # Check if target already exists (collision)
            if os.path.exists(new_folder):
                print(f"Warning: Target folder already exists, skipping rename: {new_folder}")
                return

            # Perform rename
            os.rename(old_folder, new_folder)

            # Update cache
            persist_chat._update_folder_cache(self.agent.context.id, new_folder_name)

            if is_legacy:
                print(f"Migrated chat folder: {old_folder_name} -> {new_folder_name}")
            else:
                print(f"Renamed chat folder: {old_folder_name} -> {new_folder_name}")

    except Exception as e:
        print(f"Error renaming folder: {e}")
```

### 5. Enhanced Message File Naming

**Complete rewrite of `python/extensions/hist_add_tool_result/_90_save_tool_call_file.py`:**

Key improvements:
- Extracts contextual information from tool calls
- Generates descriptive filenames with tool name and context
- Special handling for code execution, knowledge search, memory operations, subordinate agents

**Context extraction examples:**
- Code execution: Detects language and extracts function names, imports, operations
- Knowledge search: Extracts search query keywords
- Memory: Includes operation type and subject
- Subordinate agents: Includes agent name and task context

See full implementation in Section 5 of design discussion.

## Testing Strategy

### Test Scenarios

#### 1. Migration Testing
- Migrate 3 legacy folders with different titles
- Verify all data preserved
- Confirm cache contains all mappings
- Check migration marker created

#### 2. New Chat Creation
- Create new chat, verify slug-based folder
- Check cache updated
- Confirm no legacy folder created

#### 3. Title Renaming
- Test legacy folder migration on rename
- Test slug update for existing slug-based folder
- Verify no data loss

#### 4. Message File Naming
- Test various tools (code, knowledge, memory, subordinate)
- Verify descriptive filenames
- Check chronological ordering

#### 5. Edge Cases
- Empty title → defaults to "chat"
- Special characters → sanitized properly
- Very long title → truncated at word boundary
- Title collision → prevented by short_id suffix
- Folder exists → graceful handling
- Cache consistency after restart

### Manual Testing Checklist

```markdown
## Pre-Migration
- [ ] Count total chats
- [ ] Note legacy folders
- [ ] Backup: `cp -r tmp/chats tmp/chats.backup`

## Migration
- [ ] Start server (triggers migration)
- [ ] Check migration marker exists
- [ ] Verify folder renames
- [ ] Confirm chat count unchanged

## Runtime Testing
- [ ] Create new chat with slug-based name
- [ ] Change title, verify folder rename
- [ ] Run various tools, check message files
- [ ] Test performance (chat list load < 1s)
- [ ] Restart server, verify cache rebuild

## Edge Cases
- [ ] Empty title
- [ ] Special characters
- [ ] Very long title
- [ ] Same title collision
```

### Rollback Plan

```bash
# Stop server
docker-compose down

# Restore backup
rm -rf tmp/chats
mv tmp/chats.backup tmp/chats

# Remove migration marker
rm tmp/chats/.migration_slug_complete

# Start server
docker-compose up
```

## Implementation Order

**Phase 1: Foundation**
1. Create `chat_folder_utils.py`
2. Add cache infrastructure to `persist_chat.py`

**Phase 2: Migration**
3. Add `_migrate_to_slug_folders()` function
4. Integrate migration into `load_tmp_chats()`

**Phase 3: New Chat Support**
5. Modify `save_tmp_chat()` for new format
6. Modify `get_chat_folder_path()` to use cache

**Phase 4: Dynamic Renaming**
7. Update `_60_rename_chat.py`
8. Add cache updates to rename

**Phase 5: Enhanced Message Files**
9. Rewrite `_90_save_tool_call_file.py`

## Benefits

### Discoverability
- Human-readable folder names
- Descriptive message file names
- Easy grep/search: `find tmp/chats -name "*database*"`

### Organization
- Chronological sorting by timestamp
- Logical grouping by topic (slug)
- Clear tool identification in message files

### Safety
- Gradual migration (no forced changes)
- Backward compatible (legacy folders still work)
- Collision-safe (timestamp + short_id)
- Graceful error handling

### Performance
- O(1) folder lookups via cache
- Single filesystem scan at startup
- No performance degradation

### Maintainability
- Follows existing Agent Zero patterns
- Clean separation of concerns
- Consistent with v0.80 migration approach
- Well-tested edge cases

## Metrics

- **New code**: ~320 lines
- **Modified code**: ~230 lines
- **Total**: ~550 lines of changes
- **Files affected**: 4 (1 new, 3 modified)

## Risk Assessment

**Low Risk:**
- Cache implementation (in-memory, rebuilt on restart)
- Slug generation (pure function, well-tested)
- Message file naming (additive change)

**Medium Risk:**
- Migration function (one-time operation, backed up)
- Folder renaming (race conditions mitigated)

**Mitigation:**
- Comprehensive testing before production
- Backup data before migration
- Graceful error handling throughout
- Documented rollback plan

## Success Criteria

✅ **Migration successful if:**
- All existing chats load correctly
- No data loss (all messages preserved)
- Folder names are human-readable
- Cache builds without errors

✅ **New features successful if:**
- New chats use slug-based naming
- Titles auto-update folder names
- Message files have descriptive names
- Performance remains acceptable (< 1s for chat list)

✅ **Stability successful if:**
- No crashes or errors in logs
- Graceful handling of edge cases
- System works with mixed legacy/new folders
- Cache stays consistent across restarts

## Next Steps

1. Review and approve design
2. Implement Phase 1 (Foundation)
3. Test with backup data
4. Implement Phases 2-5 incrementally
5. Comprehensive testing
6. Deploy to production

## References

- Agent Zero Architecture: `docs/architecture.md`
- Agent Zero Extensibility: `docs/extensibility.md`
- Existing v0.80 Migration: `python/helpers/persist_chat.py:78-84`
- Chat Rename System: `python/extensions/monologue_start/_60_rename_chat.py`
