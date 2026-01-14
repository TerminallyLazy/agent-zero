from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict
import uuid
import threading
import os
from agent import Agent, AgentConfig, AgentContext, AgentContextType
from python.helpers import files, history
import json
from initialize import initialize_agent

from python.helpers.log import Log, LogItem
from python.helpers import chat_folder_utils

CHATS_FOLDER = "tmp/chats"
LOG_SIZE = 1000
CHAT_FILE_NAME = "chat.json"

# Cache for context_id -> folder_name mapping (in-memory)
_context_folder_cache: Dict[str, str] = {}
_cache_lock = threading.RLock()
_migration_lock = threading.Lock()


def get_chat_folder_path(ctxid: str):
    """
    Get the folder path for a chat context by ID.

    Uses cache to resolve folder name, supporting both legacy and new formats.

    Args:
        ctxid: The context ID

    Returns:
        The absolute path to the context folder
    """
    with _cache_lock:
        folder_name = _context_folder_cache.get(ctxid, ctxid)  # Fallback to ctxid for backward compat
    return files.get_abs_path(CHATS_FOLDER, folder_name)

def get_chat_msg_files_folder(ctxid: str):
    return files.get_abs_path(get_chat_folder_path(ctxid), "messages")

def save_tmp_chat(context: AgentContext):
    """Save context to the chats folder"""
    # Skip saving BACKGROUND contexts as they should be ephemeral
    if context.type == AgentContextType.BACKGROUND:
        return

    folder_name = _get_folder_name_for_context(context)
    path = _get_chat_file_path(folder_name)
    files.make_dirs(path)
    data = _serialize_context(context)
    js = _safe_json_serialize(data, ensure_ascii=False)
    files.write_file(path, js)


def save_tmp_chats():
    """Save all contexts to the chats folder"""
    for _, context in AgentContext._contexts.items():
        # Skip BACKGROUND contexts as they should be ephemeral
        if context.type == AgentContextType.BACKGROUND:
            continue
        save_tmp_chat(context)


def load_tmp_chats():
    """Load all contexts from the chats folder"""
    _convert_v080_chats()
    _migrate_to_slug_folders()
    _initialize_folder_cache()
    folders = files.list_files(CHATS_FOLDER, "*")
    json_files = []
    for folder_name in folders:
        json_files.append(_get_chat_file_path(folder_name))

    ctxids = []
    for file in json_files:
        try:
            js = files.read_file(file)
            data = json.loads(js)
            ctx = _deserialize_context(data)
            ctxids.append(ctx.id)
        except Exception as e:
            print(f"Error loading chat {file}: {e}")
    return ctxids


def _get_chat_file_path(ctxid: str):
    return files.get_abs_path(CHATS_FOLDER, ctxid, CHAT_FILE_NAME)


def _convert_v080_chats():
    json_files = files.list_files(CHATS_FOLDER, "*.json")
    for file in json_files:
        path = files.get_abs_path(CHATS_FOLDER, file)
        name = file.rstrip(".json")
        new = _get_chat_file_path(name)
        files.move_file(path, new)


def load_json_chats(jsons: list[str]):
    """Load contexts from JSON strings"""
    ctxids = []
    for js in jsons:
        data = json.loads(js)
        if "id" in data:
            del data["id"]  # remove id to get new
        ctx = _deserialize_context(data)
        ctxids.append(ctx.id)
    return ctxids


def export_json_chat(context: AgentContext):
    """Export context as JSON string"""
    data = _serialize_context(context)
    js = _safe_json_serialize(data, ensure_ascii=False)
    return js


def remove_chat(ctxid):
    """Remove a chat or task context"""
    path = get_chat_folder_path(ctxid)
    files.delete_dir(path)


def remove_msg_files(ctxid):
    """Remove all message files for a chat or task context"""
    path = get_chat_msg_files_folder(ctxid)
    files.delete_dir(path)


def _initialize_folder_cache():
    """Initialize the folder cache by scanning the tmp/chats directory. Thread-safe.

    Scans all existing chat folders and populates the cache with context_id -> folder_name mappings.
    Handles both legacy format (folder name = context_id) and new format (slug-based) folders.

    For new format folders, the context_id must be read from the chat.json file inside the folder.
    For legacy format folders, the folder name itself is the context_id.
    """
    with _cache_lock:
        global _context_folder_cache
        _context_folder_cache.clear()

        # Get all folders in the chats directory
        try:
            folders = files.list_files(CHATS_FOLDER, "*")
        except Exception:
            # Directory might not exist yet
            return

        for folder_name in folders:
            # Parse folder name to determine format
            is_new_format, legacy_context_id = chat_folder_utils.parse_folder_name(folder_name)

            if is_new_format:
                # For new format folders, we need to read chat.json to get the full context_id
                # because the folder name only contains the last 4 chars (short_id).
                # Example: folder "20240115_142530_database-setup_eeFX" → context_id "eeFXa0TR"
                chat_file_path = files.get_abs_path(CHATS_FOLDER, folder_name, CHAT_FILE_NAME)
                try:
                    js = files.read_file(chat_file_path)
                    data = json.loads(js)
                    context_id = data.get("id")
                    if context_id:
                        _context_folder_cache[context_id] = folder_name
                except Exception:
                    # Skip folders without valid chat.json
                    continue
            else:
                # Legacy format: folder name IS the context_id
                _context_folder_cache[legacy_context_id] = folder_name


def _update_folder_cache(context_id: str, folder_name: str):
    """Update the folder cache with a new or changed folder mapping. Thread-safe.

    Args:
        context_id: The context ID to update
        folder_name: The folder name associated with this context ID
    """
    with _cache_lock:
        _context_folder_cache[context_id] = folder_name


def _remove_from_folder_cache(context_id: str):
    """Remove a context_id from the folder cache. Thread-safe.

    Args:
        context_id: The context ID to remove from the cache
    """
    with _cache_lock:
        _context_folder_cache.pop(context_id, None)


def _migrate_to_slug_folders() -> int:
    """
    Migrate legacy chat folders to new slug-based format.

    This function scans the tmp/chats directory for legacy folders (those that use
    random IDs as folder names) and renames them to the new human-readable format:
    {timestamp}_{slug}_{short_id}/

    The migration is idempotent - it's safe to run multiple times. Once a folder
    has been migrated, it won't be processed again.

    Process:
        1. Scan tmp/chats/ for all folders
        2. Identify legacy folders using chat_folder_utils.is_legacy_folder()
        3. For each legacy folder:
           - Read chat.json to extract context ID, title, and created_at
           - Generate new folder name with chat_folder_utils.create_folder_name()
           - Rename the folder using os.rename()
           - Update the folder cache with _update_folder_cache()
        4. Handle errors gracefully - if one folder fails, continue with others

    Returns:
        int: The number of folders successfully migrated

    Examples:
        >>> _migrate_to_slug_folders()
        Migrating legacy chat folders...
        Migrated: eeFXa0TR -> 20240115_142530_database-setup_eeFX
        Migrated: kL9mPqR2 -> 20240115_150122_api-integration_PqR2
        Migration complete: 2 folders migrated
        2
    """
    with _migration_lock:
        migrated_count = 0

        try:
            # Get all folders in the chats directory
            try:
                folders = files.list_files(CHATS_FOLDER, "*")
            except Exception:
                # Directory might not exist yet
                return 0

            # Track if we found any legacy folders to migrate
            found_legacy = False

            for folder_name in folders:
                # Skip hidden files/folders
                if folder_name.startswith("."):
                    continue

                # Check if this is a legacy folder
                if not chat_folder_utils.is_legacy_folder(folder_name):
                    continue

                found_legacy = True

                # Get the old folder path
                old_path = files.get_abs_path(CHATS_FOLDER, folder_name)

                # Skip if not actually a directory
                if not os.path.isdir(old_path):
                    continue

                try:
                    # Read chat.json to get context information
                    chat_file_path = files.get_abs_path(old_path, CHAT_FILE_NAME)

                    if not os.path.exists(chat_file_path):
                        # Skip folders without chat.json (might be incomplete/corrupted)
                        continue

                    js = files.read_file(chat_file_path)
                    data = json.loads(js)

                    # Extract context information
                    context_id = data.get("id", folder_name)
                    # Validate context_id length before passing to create_folder_name
                    if len(context_id) < 4:
                        print(f"Warning: Invalid context_id length in {folder_name}, skipping")
                        continue
                    title = data.get("name", "chat")  # context.name is the chat title
                    created_at_str = data.get("created_at")

                    # Parse created_at timestamp
                    # The serialized format is ISO format string, need to convert to float
                    if created_at_str:
                        try:
                            created_at_dt = datetime.fromisoformat(created_at_str)
                            created_at = created_at_dt.timestamp()
                        except Exception:
                            # If parsing fails, use None (will default to current time)
                            created_at = None
                    else:
                        created_at = None

                    # Generate new folder name using the utility function
                    new_folder_name = chat_folder_utils.create_folder_name(
                        context_id=context_id,
                        title=title,
                        created_at=created_at
                    )

                    # Get the new folder path
                    new_path = files.get_abs_path(CHATS_FOLDER, new_folder_name)

                    # Check if target already exists (shouldn't happen, but be safe)
                    if os.path.exists(new_path):
                        print(f"Warning: Target folder already exists, skipping: {new_folder_name}")
                        continue

                    # Rename the folder
                    os.rename(old_path, new_path)

                    # Update the cache with the new folder name
                    _update_folder_cache(context_id, new_folder_name)

                    # Increment success counter
                    migrated_count += 1

                    # Log the migration (optional, for visibility)
                    print(f"Migrated: {folder_name} -> {new_folder_name}")

                except Exception as e:
                    # Log error but continue with other folders
                    print(f"Error migrating folder {folder_name}: {e}")
                    continue

            # Print summary if any legacy folders were found
            if found_legacy and migrated_count > 0:
                print(f"Migration complete: {migrated_count} folder(s) migrated")
            elif found_legacy and migrated_count == 0:
                print("Migration complete: No folders were successfully migrated")

        except Exception as e:
            # Catch any unexpected errors at the top level
            print(f"Error during migration: {e}")

        return migrated_count


def _get_folder_name_for_context(context: AgentContext) -> str:
    """
    Get the folder name for a chat context.

    Uses cache for O(1) lookup if context already exists.
    For new contexts, generates slug-based folder name.

    This function is the key integration point that decides whether to use
    a cached (existing) folder name or generate a new slug-based folder name.
    All folder name resolution should go through this function to ensure
    consistency and proper cache utilization.

    Args:
        context: AgentContext object with attributes:
                 - context.id: The unique context ID
                 - context.name: The chat title (used for slug generation)
                 - context.created_at: Timestamp when context was created

    Returns:
        str: The folder name (either from cache or newly generated).
             Format for new contexts: YYYYMMDD_HHMMSS_slug_shortid
             Format for cached contexts: depends on when it was created
                                        (legacy format or new slug format)

    Thread Safety:
        Uses _cache_lock to ensure thread-safe access to _context_folder_cache.

    Examples:
        >>> # Existing context (in cache) - O(1) lookup
        >>> context = AgentContext(id="eeFXa0TR", ...)
        >>> _get_folder_name_for_context(context)
        'eeFXa0TR'  # Legacy format from cache

        >>> # New context (not in cache) - generates new folder name
        >>> context = AgentContext(id="kL9mPqR2", name="API Integration", ...)
        >>> _get_folder_name_for_context(context)
        '20240115_150122_api-integration_PqR2'  # New slug format
    """
    with _cache_lock:
        # Check cache first for O(1) lookup
        cached_folder_name = _context_folder_cache.get(context.id)

        if cached_folder_name is not None:
            # Found in cache - return existing folder name
            return cached_folder_name

        # Not in cache - this is a new context
        # Generate new slug-based folder name
        created_at = context.created_at.timestamp() if context.created_at else None
        new_folder_name = chat_folder_utils.create_folder_name(
            context_id=context.id,
            title=context.name,
            created_at=created_at
        )

        # Update cache with the new mapping
        _update_folder_cache(context.id, new_folder_name)

        return new_folder_name


def _serialize_context(context: AgentContext):
    # serialize agents
    agents = []
    agent = context.agent0
    while agent:
        agents.append(_serialize_agent(agent))
        agent = agent.data.get(Agent.DATA_NAME_SUBORDINATE, None)


    data = {k: v for k, v in context.data.items() if not k.startswith("_")}
    output_data = {k: v for k, v in context.output_data.items() if not k.startswith("_")}

    return {
        "id": context.id,
        "name": context.name,
        "created_at": (
            context.created_at.isoformat()
            if context.created_at
            else datetime.fromtimestamp(0).isoformat()
        ),
        "type": context.type.value,
        "last_message": (
            context.last_message.isoformat()
            if context.last_message
            else datetime.fromtimestamp(0).isoformat()
        ),
        "agents": agents,
        "streaming_agent": (
            context.streaming_agent.number if context.streaming_agent else 0
        ),
        "log": _serialize_log(context.log),
        "data": data,
        "output_data": output_data,
    }


def _serialize_agent(agent: Agent):
    data = {k: v for k, v in agent.data.items() if not k.startswith("_")}

    history = agent.history.serialize()

    return {
        "number": agent.number,
        "data": data,
        "history": history,
    }


def _serialize_log(log: Log):
    return {
        "guid": log.guid,
        "logs": [
            item.output() for item in log.logs[-LOG_SIZE:]
        ],  # serialize LogItem objects
        "progress": log.progress,
        "progress_no": log.progress_no,
    }


def _deserialize_context(data):
    config = initialize_agent()
    log = _deserialize_log(data.get("log", None))

    context = AgentContext(
        config=config,
        id=data.get("id", None),  # get new id
        name=data.get("name", None),
        created_at=(
            datetime.fromisoformat(
                # older chats may not have created_at - backcompat
                data.get("created_at", datetime.fromtimestamp(0).isoformat())
            )
        ),
        type=AgentContextType(data.get("type", AgentContextType.USER.value)),
        last_message=(
            datetime.fromisoformat(
                data.get("last_message", datetime.fromtimestamp(0).isoformat())
            )
        ),
        log=log,
        paused=False,
        data=data.get("data", {}),
        output_data=data.get("output_data", {}),
        # agent0=agent0,
        # streaming_agent=straming_agent,
    )

    agents = data.get("agents", [])
    agent0 = _deserialize_agents(agents, config, context)
    streaming_agent = agent0
    while streaming_agent and streaming_agent.number != data.get("streaming_agent", 0):
        streaming_agent = streaming_agent.data.get(Agent.DATA_NAME_SUBORDINATE, None)

    context.agent0 = agent0
    context.streaming_agent = streaming_agent

    return context


def _deserialize_agents(
    agents: list[dict[str, Any]], config: AgentConfig, context: AgentContext
) -> Agent:
    prev: Agent | None = None
    zero: Agent | None = None

    for ag in agents:
        current = Agent(
            number=ag["number"],
            config=config,
            context=context,
        )
        current.data = ag.get("data", {})
        current.history = history.deserialize_history(
            ag.get("history", ""), agent=current
        )
        if not zero:
            zero = current

        if prev:
            prev.set_data(Agent.DATA_NAME_SUBORDINATE, current)
            current.set_data(Agent.DATA_NAME_SUPERIOR, prev)
        prev = current

    return zero or Agent(0, config, context)


# def _deserialize_history(history: list[dict[str, Any]]):
#     result = []
#     for hist in history:
#         content = hist.get("content", "")
#         msg = (
#             HumanMessage(content=content)
#             if hist.get("type") == "human"
#             else AIMessage(content=content)
#         )
#         result.append(msg)
#     return result


def _deserialize_log(data: dict[str, Any]) -> "Log":
    log = Log()
    log.guid = data.get("guid", str(uuid.uuid4()))
    log.set_initial_progress()

    # Deserialize the list of LogItem objects
    i = 0
    for item_data in data.get("logs", []):
        log.logs.append(LogItem(
            log=log,  # restore the log reference
            no=i,  # item_data["no"],
            type=item_data["type"],
            heading=item_data.get("heading", ""),
            content=item_data.get("content", ""),
            kvps=OrderedDict(item_data["kvps"]) if item_data["kvps"] else None,
            temp=item_data.get("temp", False),
            # Pass metrics directly to constructor
            timestamp=item_data.get("timestamp", 0.0),
            duration_ms=item_data.get("duration_ms"),
            agent_number=item_data.get("agent_number", 0),
        ))
        log.updates.append(i)
        i += 1

    return log


def _safe_json_serialize(obj, **kwargs):
    def serializer(o):
        if isinstance(o, dict):
            return {k: v for k, v in o.items() if is_json_serializable(v)}
        elif isinstance(o, (list, tuple)):
            return [item for item in o if is_json_serializable(item)]
        elif is_json_serializable(o):
            return o
        else:
            return None  # Skip this property

    def is_json_serializable(item):
        try:
            json.dumps(item)
            return True
        except (TypeError, OverflowError):
            return False

    return json.dumps(obj, default=serializer, **kwargs)


