from typing import Any
from python.helpers.extension import Extension
from python.helpers import files, persist_chat
import os, re
import datetime

LEN_MIN = 500

class SaveToolCallFile(Extension):
    async def execute(self, data: dict[str, Any] | None = None, **kwargs):
        if not data:
            return

        # get tool call result
        result = data.get("tool_result") if isinstance(data, dict) else None
        if result is None:
            return

        # skip short results
        if len(str(result)) < LEN_MIN:
            return

        # message files directory
        msgs_folder = persist_chat.get_chat_msg_files_folder(self.agent.context.id)
        os.makedirs(msgs_folder, exist_ok=True)

        # get tool name
        tool_name = data.get("tool_name", "unknown")

        # extract context from tool result
        context = self._extract_context(tool_name, result)

        # generate timestamp
        timestamp = self._generate_timestamp()

        # get next sequence number
        seq = self._get_next_sequence(msgs_folder)

        # create descriptive filename
        filename = self._create_filename(timestamp, seq, tool_name, context)
        new_file = files.get_abs_path(msgs_folder, filename)

        # write the file
        files.write_file(new_file, result)

        # add the path to the history
        data["file"] = new_file

    def _generate_timestamp(self) -> str:
        """Generate timestamp in YYYYMMDD_HHMMSS format (UTC).

        Returns:
            Timestamp string in format: 20240115_143022
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        return now.strftime("%Y%m%d_%H%M%S")

    def _get_next_sequence(self, msgs_folder: str) -> int:
        """Get the next sequence number for the current timestamp.

        Args:
            msgs_folder: Path to the messages folder

        Returns:
            Next sequence number (starting from 1)
        """
        # Count existing files to determine next sequence
        # This is simple and works well for our use case
        existing_files = os.listdir(msgs_folder) if os.path.exists(msgs_folder) else []
        return len(existing_files) + 1

    def _extract_context(self, tool_name: str, result: str) -> str:
        """Extract meaningful context from the tool result.

        Args:
            tool_name: Name of the tool that generated the result
            result: The tool's result string

        Returns:
            A short context string describing what the tool did
        """
        result_str = str(result)

        # Handle code_execution_tool - extract runtime/language
        if tool_name == "code_execution_tool":
            # Look for runtime indicators in the result
            if "python>" in result_str.lower():
                return "python"
            elif "node>" in result_str.lower():
                return "nodejs"
            elif "bash>" in result_str.lower() or "ps>" in result_str.lower():
                return "shell"
            else:
                return "exec"

        # Handle knowledge_tool - extract search query from result
        elif tool_name == "knowledge_tool":
            # Try to find the query from the content
            # The result typically contains search results, so we look for patterns
            lines = result_str.split('\n')
            for line in lines[:5]:  # Check first few lines
                if line.strip() and len(line) < 100:
                    # Extract first few meaningful words
                    words = re.findall(r'\b\w+\b', line.lower())
                    if words:
                        context = '_'.join(words[:3])  # Take first 3 words
                        return self._sanitize_context(context)
            return "search"

        # Handle call_subordinate - extract purpose/task
        elif tool_name == "call_subordinate":
            # Look for task indicators in the result
            lines = result_str.split('\n')
            for line in lines[:5]:  # Check first few lines
                line = line.strip()
                if line and len(line) < 100:
                    # Extract meaningful words
                    words = re.findall(r'\b\w+\b', line.lower())
                    if words:
                        context = '_'.join(words[:3])
                        return self._sanitize_context(context)
            return "delegate"

        # Default: use tool name
        else:
            return tool_name.replace("_tool", "").replace("_", "-")

    def _sanitize_context(self, context: str, max_length: int = 30) -> str:
        """Sanitize context string for use in filename.

        Similar to slug generation but for context strings.
        Removes special characters and limits length.

        Args:
            context: The context string to sanitize
            max_length: Maximum length of the sanitized string

        Returns:
            Sanitized context string safe for use in filenames
        """
        if not context:
            return "result"

        # Convert to lowercase
        sanitized = context.lower()

        # Replace spaces and underscores with hyphens
        sanitized = sanitized.replace(" ", "-").replace("_", "-")

        # Remove non-alphanumeric characters (except hyphens)
        sanitized = re.sub(r'[^a-z0-9\-]', '', sanitized)

        # Remove consecutive hyphens
        sanitized = re.sub(r'-+', '-', sanitized)

        # Trim hyphens from start and end
        sanitized = sanitized.strip('-')

        # Truncate if needed
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip('-')

        return sanitized if sanitized else "result"

    def _create_filename(self, timestamp: str, seq: int, tool_name: str, context: str) -> str:
        """Create a descriptive filename for the tool result.

        Format: {timestamp}_{seq}_{tool_name}_{context}.txt
        Example: 20240115_143022_001_code_execution_python.txt

        Args:
            timestamp: Timestamp string in YYYYMMDD_HHMMSS format
            seq: Sequence number
            tool_name: Name of the tool
            context: Context extracted from the result

        Returns:
            Formatted filename string
        """
        # Format sequence as 3-digit number
        seq_str = f"{seq:03d}"

        # Sanitize tool name
        tool_name_clean = tool_name.replace("_tool", "").replace("_", "-")

        # Build filename
        filename = f"{timestamp}_{seq_str}_{tool_name_clean}_{context}.txt"

        return filename
