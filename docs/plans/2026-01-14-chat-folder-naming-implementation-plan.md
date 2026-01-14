# Chat Folder Naming Implementation Plan

**Date:** 2026-01-14
**Worktree:** `.worktrees/implement-chat-folder-naming`
**Branch:** `implement/chat-folder-naming`
**Design Doc:** `docs/plans/2026-01-14-chat-folder-naming-design.md`

## Quick Reference

**Files to Create:**
- [ ] `python/helpers/chat_folder_utils.py` (~120 lines)

**Files to Modify:**
- [ ] `python/helpers/persist_chat.py` (~150 lines changed/added)
- [ ] `python/extensions/monologue_start/_60_rename_chat.py` (~80 lines changed/added)
- [ ] `python/extensions/hist_add_tool_result/_90_save_tool_call_file.py` (~200 lines, complete rewrite)

**Total:** ~550 lines of code changes

## Implementation Phases

### Phase 1: Foundation (No Breaking Changes)

#### Task 1.1: Create `chat_folder_utils.py`

**Location:** `python/helpers/chat_folder_utils.py`

**Implementation checklist:**
- [ ] Add imports: `re`, `os`, `datetime`, `typing.Tuple`
- [ ] Implement `generate_slug(title, max_length=30)`:
  - [ ] Convert to lowercase
  - [ ] Replace spaces/underscores with hyphens
  - [ ] Remove non-alphanumeric (except hyphens)
  - [ ] Remove consecutive hyphens
  - [ ] Trim hyphens from start/end
  - [ ] Truncate at word boundary
  - [ ] Fallback to "chat" if empty
- [ ] Implement `create_folder_name(context_id, title, created_at)`:
  - [ ] Generate timestamp in `YYYYMMDD_HHMMSS` format
  - [ ] Generate slug from title
  - [ ] Extract last 4 chars of context_id for short_id
  - [ ] Return `f"{timestamp}_{slug}_{short_id}"`
- [ ] Implement `parse_folder_name(folder_name)`:
  - [ ] Regex pattern: `^\d{8}_\d{6}_[a-z0-9\-]+_([a-zA-Z0-9]{4})$`
  - [ ] Return `(is_new_format, context_id)`
- [ ] Implement `is_legacy_folder(folder_name)`:
  - [ ] Call `parse_folder_name()` and return `not is_new`

**Testing:**
```python
# Test cases to validate
generate_slug("Database Setup")  # -> "database-setup"
generate_slug("API Integration (v2)")  # -> "api-integration-v2"
generate_slug("Bug: User can't login!")  # -> "bug-user-cant-login"
generate_slug("")  # -> "chat"
generate_slug("This is a very long title that exceeds...")  # -> truncated

create_folder_name("eeFXa0TR", "Database Setup", 1705334730.0)
# -> "20240115_142530_database-setup_eeFX"

parse_folder_name("20240115_142530_database-setup_eeFX")  # -> (True, None)
parse_folder_name("eeFXa0TR")  # -> (False, "eeFXa0TR")
```

#### Task 1.2: Add Cache Infrastructure

**Location:** `python/helpers/persist_chat.py`

**Implementation checklist:**
- [ ] Add module-level cache variables at top of file:
  ```python
  _context_folder_cache = {}
  _cache_initialized = False
  ```
- [ ] Add import: `from python.helpers import chat_folder_utils`
- [ ] Implement `_initialize_folder_cache()`:
  - [ ] Check if already initialized, return early
  - [ ] Clear cache
  - [ ] List all folders in CHATS_FOLDER
  - [ ] For each folder:
    - [ ] Skip if starts with "."
    - [ ] Skip if not a directory
    - [ ] Parse folder name with `chat_folder_utils.parse_folder_name()`
    - [ ] If new format: read chat.json to get context_id
    - [ ] If legacy: folder name IS context_id
    - [ ] Add to cache: `_context_folder_cache[context_id] = folder_name`
  - [ ] Set `_cache_initialized = True`
  - [ ] Print count of loaded chats
- [ ] Implement `_update_folder_cache(context_id, folder_name)`:
  - [ ] Update cache: `_context_folder_cache[context_id] = folder_name`
- [ ] Implement `_remove_from_folder_cache(context_id)`:
  - [ ] Remove from cache: `_context_folder_cache.pop(context_id, None)`

**Testing:**
- [ ] Verify cache initializes on first access
- [ ] Verify cache contains all existing chats
- [ ] Verify cache updates on new chat creation

---

### Phase 2: Migration (One-Time Operation)

#### Task 2.1: Implement Migration Function

**Location:** `python/helpers/persist_chat.py`

**Implementation checklist:**
- [ ] Implement `_migrate_to_slug_folders()`:
  - [ ] Check for migration marker: `.migration_slug_complete`
  - [ ] If marker exists, return early (already migrated)
  - [ ] Print start message
  - [ ] List all folders in CHATS_FOLDER
  - [ ] For each folder:
    - [ ] Skip if starts with "."
    - [ ] Skip if not legacy format
    - [ ] Skip if not a directory
    - [ ] Read chat.json to get: id, name, created_at
    - [ ] Generate new folder name with `chat_folder_utils.create_folder_name()`
    - [ ] Rename folder: `files.move_file(old_path, new_path)`
    - [ ] Increment migration counter
    - [ ] Print migration message
    - [ ] Handle exceptions gracefully (continue with next folder)
  - [ ] Create migration marker file with timestamp and count
  - [ ] Print completion message with count

**Error handling:**
- [ ] Wrap migration in try-except
- [ ] Log errors but don't fail entire migration
- [ ] Continue with remaining folders if one fails

**Testing:**
- [ ] Create test legacy folders with chat.json
- [ ] Run migration
- [ ] Verify folders renamed correctly
- [ ] Verify marker file created
- [ ] Verify re-running migration is no-op

#### Task 2.2: Integrate Migration

**Location:** `python/helpers/persist_chat.py`

**Modify `load_tmp_chats()`:**
- [ ] After `_convert_v080_chats()`, call `_migrate_to_slug_folders()`
- [ ] After migration, call `_initialize_folder_cache()`
- [ ] Use cache to load chats instead of listing folders directly

**Implementation:**
```python
def load_tmp_chats():
    """Load all contexts from the chats folder"""
    _convert_v080_chats()  # Existing v0.80 migration
    _migrate_to_slug_folders()  # NEW: Slug migration
    _initialize_folder_cache()  # NEW: Build cache

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

---

### Phase 3: New Chat Support

#### Task 3.1: Implement Helper Function

**Location:** `python/helpers/persist_chat.py`

**Implementation:**
- [ ] Add `_get_folder_name_for_context(context)`:
  - [ ] Check if context.id exists in cache
  - [ ] If yes: return cached folder name
  - [ ] If no: create new slug-based folder name
  - [ ] Use `chat_folder_utils.create_folder_name()`
  - [ ] Return folder name

```python
def _get_folder_name_for_context(context: AgentContext) -> str:
    """
    Determine the folder name for a context.
    - For existing chats: use cached folder name
    - For new chats: create slug-based name
    """
    if context.id in _context_folder_cache:
        return _context_folder_cache[context.id]

    folder_name = chat_folder_utils.create_folder_name(
        context_id=context.id,
        title=context.name,
        created_at=context.created_at
    )

    return folder_name
```

#### Task 3.2: Modify save_tmp_chat()

**Location:** `python/helpers/persist_chat.py`

**Modifications:**
- [ ] Replace direct folder path construction
- [ ] Use `_get_folder_name_for_context(context)` to get folder name
- [ ] Construct full path: `files.get_abs_path(CHATS_FOLDER, folder_name)`
- [ ] After creating directory, update cache: `_update_folder_cache(context.id, folder_name)`

```python
def save_tmp_chat(context: AgentContext):
    """Save context to the chats folder"""
    if context.type == AgentContextType.BACKGROUND:
        return

    # Determine folder name (legacy or new format)
    folder_name = _get_folder_name_for_context(context)
    folder_path = files.get_abs_path(CHATS_FOLDER, folder_name)

    # Create directory
    files.make_dirs(folder_path)

    # Update cache
    _update_folder_cache(context.id, folder_name)

    # Serialize and save
    chat_file = os.path.join(folder_path, CHAT_FILE_NAME)
    data = _serialize_context(context)
    js = _safe_json_serialize(data, ensure_ascii=False)
    files.write_file(chat_file, js)
```

#### Task 3.3: Modify get_chat_folder_path()

**Location:** `python/helpers/persist_chat.py`

**Simplify using cache:**
- [ ] Remove filesystem scanning logic
- [ ] Use cache for O(1) lookup
- [ ] Fallback to legacy path if not in cache (for new chats)

```python
def get_chat_folder_path(ctxid: str) -> str:
    """
    Get the folder path for a context by ID.
    Uses cache for fast O(1) lookup.
    """
    if not _cache_initialized:
        _initialize_folder_cache()

    folder_name = _context_folder_cache.get(ctxid)
    if folder_name:
        return files.get_abs_path(CHATS_FOLDER, folder_name)

    # Not in cache - return legacy path (caller will create if needed)
    return files.get_abs_path(CHATS_FOLDER, ctxid)
```

---

### Phase 4: Dynamic Renaming

#### Task 4.1: Update _60_rename_chat.py

**Location:** `python/extensions/monologue_start/_60_rename_chat.py`

**Imports to add:**
- [ ] `import os`
- [ ] `from python.helpers import chat_folder_utils`

**Add new method:**
```python
async def _rename_folder_if_needed(self, old_folder: str, old_folder_name: str, new_title: str):
    """
    Rename the chat folder if title changed.
    - New format folders: rename with updated slug
    - Legacy format folders: migrate to new format
    """
    try:
        is_legacy = chat_folder_utils.is_legacy_folder(old_folder_name)

        new_folder_name = chat_folder_utils.create_folder_name(
            context_id=self.agent.context.id,
            title=new_title,
            created_at=self.agent.context.created_at
        )

        if new_folder_name != old_folder_name:
            new_folder = os.path.join(os.path.dirname(old_folder), new_folder_name)

            if os.path.exists(new_folder):
                print(f"Warning: Target folder already exists: {new_folder}")
                return

            os.rename(old_folder, new_folder)
            persist_chat._update_folder_cache(self.agent.context.id, new_folder_name)

            if is_legacy:
                print(f"Migrated: {old_folder_name} -> {new_folder_name}")
            else:
                print(f"Renamed: {old_folder_name} -> {new_folder_name}")

    except Exception as e:
        print(f"Error renaming folder: {e}")
```

**Modify change_name():**
- [ ] Before updating context.name, store old folder path
- [ ] After updating context.name, call `_rename_folder_if_needed()`
- [ ] Then save context with `persist_chat.save_tmp_chat()`

```python
async def change_name(self):
    try:
        # ... existing title generation code ...

        if new_name:
            if len(new_name) > 40:
                new_name = new_name[:40] + "..."

            # Store old folder before rename
            old_folder = persist_chat.get_chat_folder_path(self.agent.context.id)
            old_folder_name = os.path.basename(old_folder)

            # Update context name
            self.agent.context.name = new_name

            # Rename folder if needed
            await self._rename_folder_if_needed(old_folder, old_folder_name, new_name)

            # Save updated context
            persist_chat.save_tmp_chat(self.agent.context)
    except Exception as e:
        print(f"Error renaming chat: {e}")
```

---

### Phase 5: Enhanced Message File Naming

#### Task 5.1: Rewrite _90_save_tool_call_file.py

**Location:** `python/extensions/hist_add_tool_result/_90_save_tool_call_file.py`

**Complete rewrite required. Implementation checklist:**

- [ ] Keep `LEN_MIN = 500` constant
- [ ] Modify `execute()` method:
  - [ ] Get tool_name and tool_args from data
  - [ ] Call `_extract_context(tool_name, tool_args, result)`
  - [ ] Generate timestamp and sequence number
  - [ ] Create filename: `f"{timestamp}_{seq:03d}_{tool_slug}_{context_slug}.txt"`

- [ ] Implement `_extract_context(tool_name, tool_args, result)`:
  - [ ] Handle code execution tools:
    - [ ] Extract language from args
    - [ ] Call `_extract_code_context(code)` for context
    - [ ] Return `f"{language}_{code_context}"`
  - [ ] Handle knowledge/search tools:
    - [ ] Extract query from args
    - [ ] Take first 3 words
    - [ ] Return `"search_" + "_".join(words)`
  - [ ] Handle memory tools:
    - [ ] Extract operation and query
    - [ ] Return `f"{operation}_" + key_words`
  - [ ] Handle subordinate agents:
    - [ ] Extract agent_name or message
    - [ ] Return cleaned agent name or first words of message
  - [ ] Handle response tool:
    - [ ] Extract first 3 words of response
  - [ ] Default: return "action"

- [ ] Implement `_extract_code_context(code)`:
  - [ ] Look for function definitions in Python
  - [ ] Look for key imports (pandas, requests, numpy)
  - [ ] Look for bash commands (apt-get, pip, npm, git)
  - [ ] Look for file operations (open, write, read)
  - [ ] Return descriptive context (e.g., "pandas_analysis", "pip_install", "git_operation")
  - [ ] Default: "script" or "complex_script" based on length

- [ ] Implement `_sanitize_tool_name(tool_name)`:
  - [ ] Remove "_tool" suffix
  - [ ] Keep only alphanumeric and underscores
  - [ ] Limit to 15 chars

- [ ] Implement `_sanitize_context(context)`:
  - [ ] Lowercase and replace spaces with underscores
  - [ ] Keep only alphanumeric and underscores
  - [ ] Limit to 25 chars
  - [ ] Fallback to "action" if empty

**Testing examples:**
```python
# Code execution
tool_name = "code_execution_tool"
tool_args = {"language": "python", "code": "import pandas as pd\ndf = pd.read_csv('data.csv')"}
# Expected: "20240115_142530_001_code_python_pandas_analysis.txt"

# Knowledge search
tool_name = "knowledge_tool"
tool_args = {"query": "How to setup PostgreSQL database"}
# Expected: "20240115_143000_002_knowledge_search_how_to_setup.txt"

# Memory save
tool_name = "memory_tool"
tool_args = {"operation": "save", "query": "API credentials for service X"}
# Expected: "20240115_143030_003_memory_save_api_credentials.txt"
```

---

## Testing Checklist

### Unit Testing

- [ ] Test slug generation with various inputs
- [ ] Test folder name creation with timestamps
- [ ] Test folder name parsing (new vs legacy)
- [ ] Test context extraction for each tool type
- [ ] Test filename sanitization

### Integration Testing

**In Docker environment:**

- [ ] Start fresh Agent Zero instance
- [ ] Verify migration runs on startup
- [ ] Check migration marker created
- [ ] Create new chat, verify slug-based folder
- [ ] Change chat title, verify folder renamed
- [ ] Execute various tools, verify message filenames
- [ ] Restart Agent Zero, verify cache rebuilds
- [ ] Verify all chats load correctly

### Edge Case Testing

- [ ] Empty title → defaults to "chat"
- [ ] Special characters in title → sanitized
- [ ] Very long title → truncated at word boundary
- [ ] Same title, same second → different short_id prevents collision
- [ ] Folder already exists → logged warning, graceful handling
- [ ] Cache consistency after multiple restarts

---

## Commit Strategy

**Commit after each phase:**

1. **Phase 1:** `feat: add chat folder utilities and cache infrastructure`
2. **Phase 2:** `feat: add migration for slug-based folder naming`
3. **Phase 3:** `feat: support slug-based folders for new chats`
4. **Phase 4:** `feat: auto-rename folders on title change`
5. **Phase 5:** `feat: enhance message file naming with context`

**Final commit:** `feat: complete chat folder naming implementation`

---

## Rollback Plan

If issues occur:

```bash
# From main repo
cd /Users/lazy/Projects/agent-zero

# Remove worktree
git worktree remove .worktrees/implement-chat-folder-naming

# Delete branch if needed
git branch -D implement/chat-folder-naming

# Restore from backup if migration caused issues
# (User should backup tmp/chats before testing)
```

---

## Success Metrics

✅ **Implementation complete when:**
- [ ] All 4 files modified/created
- [ ] All tests passing
- [ ] Migration successfully renames existing chats
- [ ] New chats use slug-based naming
- [ ] Title changes update folder names
- [ ] Message files have descriptive names
- [ ] No performance degradation (< 1s chat list load)
- [ ] No errors in Docker logs

---

## Next Steps After Implementation

1. Test thoroughly in Docker environment
2. Create backup of tmp/chats before production use
3. Run migration on production data
4. Monitor for any issues
5. Create PR with:
   - Design document
   - Implementation plan
   - Test results
   - Before/after screenshots
