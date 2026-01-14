import re
import os
import datetime
from typing import Tuple


def generate_slug(title: str, max_length: int = 30) -> str:
    """Generate a URL-friendly slug from a chat title.

    Converts a human-readable title into a lowercase, hyphenated slug suitable
    for use in folder names. Handles special characters, consecutive hyphens,
    and truncates at word boundaries when necessary.

    Args:
        title: The chat title to convert into a slug.
        max_length: Maximum length of the resulting slug (default: 30).
                   Truncation prefers word boundaries (hyphens) if possible.

    Returns:
        A URL-friendly slug string. Returns "chat" if the input produces an empty slug.

    Examples:
        >>> generate_slug("Database Setup")
        'database-setup'
        >>> generate_slug("API Integration (v2)")
        'api-integration-v2'
        >>> generate_slug("Bug: User can't login!")
        'bug-user-cant-login'
        >>> generate_slug("")
        'chat'
    """
    if not title:
        return "chat"

    # Convert to lowercase
    slug = title.lower()

    # Replace spaces and underscores with hyphens
    slug = slug.replace(" ", "-").replace("_", "-")

    # Remove non-alphanumeric characters (except hyphens)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)

    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Trim hyphens from start and end
    slug = slug.strip('-')

    # Fallback if slug is empty after sanitization
    if not slug:
        return "chat"

    # Truncate at word boundary if needed
    if len(slug) > max_length:
        # If we're already at or under max_length, return as-is
        truncated = slug[:max_length]

        # Try to find a hyphen in the second half to cut at a word boundary
        second_half_start = max_length // 2
        last_hyphen = truncated.rfind('-', second_half_start)

        if last_hyphen > second_half_start:
            # Found a good cutting point in the second half
            truncated = truncated[:last_hyphen]

        slug = truncated.rstrip('-')

    return slug if slug else "chat"


def create_folder_name(context_id: str, title: str = None, created_at: float = None) -> str:
    """Create a new-format folder name with timestamp, slug, and short ID.

    Generates a folder name in the format: YYYYMMDD_HHMMSS_slug_shortid
    This format is sortable by creation time and includes human-readable context.

    Args:
        context_id: The full context ID (e.g., "eeFXa0TR"). The last 4 characters
                   will be used as the short ID suffix.
        title: Optional chat title to convert into a slug. If None, uses "chat".
        created_at: Optional Unix timestamp (float) for the folder creation time.
                   If None, uses the current time.

    Returns:
        A folder name string in the format: YYYYMMDD_HHMMSS_slug_shortid

    Examples:
        >>> create_folder_name("eeFXa0TR", "Database Setup", 1705334730.0)
        '20240115_142530_database-setup_eeFX'
        >>> create_folder_name("abc123XY", None, 1705334730.0)
        '20240115_142530_chat_23XY'
    """
    # Validate context_id has at least 4 characters
    assert len(context_id) >= 4, f"context_id must be at least 4 characters, got: {context_id}"

    # Handle None values
    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).timestamp()

    if title is None:
        title = "chat"

    # Generate timestamp in YYYYMMDD_HHMMSS format (UTC)
    dt = datetime.datetime.fromtimestamp(created_at, tz=datetime.timezone.utc)
    timestamp = dt.strftime("%Y%m%d_%H%M%S")

    # Generate slug from title
    slug = generate_slug(title)

    # Extract last 4 characters of context_id for short_id
    short_id = context_id[-4:]

    # Return formatted folder name
    return f"{timestamp}_{slug}_{short_id}"


def parse_folder_name(folder_name: str) -> Tuple[bool, str]:
    """Parse a folder name to determine if it's new or legacy format.

    Checks if the folder name matches the new format pattern and extracts
    information accordingly. The new format is: YYYYMMDD_HHMMSS_slug_shortid

    Args:
        folder_name: The folder name to parse (just the folder name, not the full path).

    Returns:
        A tuple of (is_new_format, context_id_or_none):
        - If new format: (True, None) - context ID must be read from chat.json
        - If legacy format: (False, folder_name) - folder name IS the context ID

    Examples:
        >>> parse_folder_name("20240115_142530_database-setup_eeFX")
        (True, None)
        >>> parse_folder_name("eeFXa0TR")
        (False, 'eeFXa0TR')
    """
    # Regex pattern for new format: YYYYMMDD_HHMMSS_slug_shortid
    # - 8 digits (date)
    # - underscore
    # - 6 digits (time)
    # - underscore
    # - slug (lowercase letters, numbers, hyphens)
    # - underscore
    # - 4 alphanumeric characters (short ID, case-sensitive)
    pattern = r'^\d{8}_\d{6}_[a-z0-9\-]+_([a-zA-Z0-9]{4})$'

    match = re.match(pattern, folder_name)

    if match:
        # New format: context ID must be read from chat.json
        return (True, None)
    else:
        # Legacy format: folder name IS the context ID
        return (False, folder_name)


def is_legacy_folder(folder_name: str) -> bool:
    """Check if a folder name uses the legacy format.

    Legacy format folders use a random ID as the folder name (e.g., "eeFXa0TR").
    New format folders use the pattern: YYYYMMDD_HHMMSS_slug_shortid

    Args:
        folder_name: The folder name to check.

    Returns:
        True if the folder uses legacy format, False if it uses new format.

    Examples:
        >>> is_legacy_folder("20240115_142530_database-setup_eeFX")
        False
        >>> is_legacy_folder("eeFXa0TR")
        True
    """
    is_new, _ = parse_folder_name(folder_name)
    return not is_new
