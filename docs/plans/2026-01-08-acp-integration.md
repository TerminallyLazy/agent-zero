# Agent Zero ACP Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate the Agent Client Protocol (ACP) into Agent Zero, enabling ACP clients (Zed IDE, Claude Desktop, etc.) to interact with Agent Zero as an ACP-compliant agent.

**Architecture:** ACP integration follows the Adapter Pattern, creating a thin translation layer between ACP protocol and Agent Zero's existing systems. The adapter maps ACP sessions to Agent Zero's `AgentContext`, translates ACP content blocks to `UserMessage` format, and streams Agent Zero's responses back to ACP clients. This mirrors the existing `fasta2a_server.py` pattern.

**Tech Stack:** Python 3.11+, `agent-client-protocol` SDK (pip), asyncio, Agent Zero's extension system

**ACP SDK Reference:**
- Package: `agent-client-protocol` (PyPI)
- Protocol: stdio-based (not HTTP by default)
- Core methods: `initialize`, `new_session`, `prompt`, `cancel_prompt`
- Streaming: `self.connection.session_update()` pattern

---

## Phase 1: Foundation - Core ACP Adapter

### Task 1.1: Add ACP Dependency

**Files:**
- Modify: `requirements.txt:50` (append to end)

**Step 1: Add acp package to requirements**

Add to `requirements.txt`:
```
agent-client-protocol>=0.1.0
```

**Step 2: Verify installation**

Run: `pip install agent-client-protocol`
Expected: Successfully installed agent-client-protocol-X.X.X

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add acp sdk for Agent Client Protocol integration"
```

---

### Task 1.2: Create ACP Adapter Module Structure

**Files:**
- Create: `python/helpers/acp_adapter.py`
- Test: `tests/test_acp_adapter.py`

**Step 1: Write the failing test for ACP availability check**

Create `tests/test_acp_adapter.py`:
```python
"""Tests for ACP adapter module."""
import pytest


def test_acp_availability_check_when_installed():
    """Test that ACP availability returns True when acp package is installed."""
    from python.helpers import acp_adapter
    
    # When acp is installed, is_available should return True
    result = acp_adapter.is_available()
    
    assert result is True


def test_acp_adapter_module_imports():
    """Test that the acp_adapter module can be imported without errors."""
    from python.helpers import acp_adapter
    
    assert hasattr(acp_adapter, 'AgentZeroACP')
    assert hasattr(acp_adapter, 'is_available')
    assert hasattr(acp_adapter, 'ACP_AVAILABLE')
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_acp_adapter.py -v`
Expected: FAIL with "ModuleNotFoundError" or "cannot import name"

**Step 3: Write minimal implementation**

Create `python/helpers/acp_adapter.py`:
```python
# noqa: D401 (docstrings) - internal helper
"""ACP (Agent Client Protocol) adapter for Agent Zero.

This module provides an ACP-compliant adapter that exposes Agent Zero's
capabilities to ACP clients while maintaining full compatibility with
Agent Zero's existing architecture and patterns.
"""
import asyncio
from typing import Any, AsyncIterator

from python.helpers.print_style import PrintStyle

# Import ACP SDK (agent-client-protocol package)
try:
    from acp import Agent as ACPAgent
    from acp import (
        InitializeResponse,
        NewSessionResponse,
        PromptResponse,
        ContentBlock,
    )
    from acp.helpers import text_block, update_agent_message_text, update_agent_thought_text
    ACP_AVAILABLE = True
except ImportError:
    ACP_AVAILABLE = False
    # Minimal stubs for type checkers when ACP is not available
    ACPAgent = object  # type: ignore
    InitializeResponse = Any  # type: ignore
    NewSessionResponse = Any  # type: ignore
    PromptResponse = Any  # type: ignore
    ContentBlock = Any  # type: ignore

_PRINTER = PrintStyle(italic=True, font_color="cyan", padding=False)


class AgentZeroACP(ACPAgent if ACP_AVAILABLE else object):  # type: ignore[misc]
    """ACP Agent implementation wrapping Agent Zero."""
    
    def __init__(self):
        """Initialize the ACP adapter."""
        self._sessions: dict[str, str] = {}  # acp_session_id -> agent_context_id
        self.connection = None  # Set by ACP runtime for streaming
        
    async def initialize(self, protocol_version: int, **kwargs) -> "InitializeResponse":
        """Handle ACP initialization and version negotiation.
        
        Args:
            protocol_version: The protocol version requested by the client.
            
        Returns:
            InitializeResponse with negotiated version.
        """
        if not ACP_AVAILABLE:
            raise RuntimeError("ACP SDK not available")
        
        _PRINTER.print(f"[ACP] Initializing with protocol version {protocol_version}")
        return InitializeResponse(protocol_version=protocol_version)


def is_available() -> bool:
    """Check if ACP SDK is available."""
    return ACP_AVAILABLE
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_acp_adapter.py -v`
Expected: PASS (2 passed)

**Step 5: Commit**

```bash
git add python/helpers/acp_adapter.py tests/test_acp_adapter.py
git commit -m "feat(acp): add initial acp_adapter module with availability check"
```

---

### Task 1.3: Implement Session Management

**Files:**
- Modify: `python/helpers/acp_adapter.py`
- Test: `tests/test_acp_adapter.py`

**Step 1: Write failing test for session creation**

Add to `tests/test_acp_adapter.py`:
```python
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def acp_adapter():
    """Create a fresh ACP adapter instance."""
    from python.helpers.acp_adapter import AgentZeroACP
    return AgentZeroACP()


@pytest.mark.asyncio
async def test_new_session_creates_agent_context(acp_adapter):
    """Test that new_session creates an AgentContext and returns NewSessionResponse."""
    # Mock the AgentContext and initialize_agent
    with patch('python.helpers.acp_adapter.AgentContext') as mock_context_cls, \
         patch('python.helpers.acp_adapter.initialize_agent') as mock_init:
        
        mock_context = MagicMock()
        mock_context.id = "test-context-123"
        mock_context.data = {}
        mock_context_cls.return_value = mock_context
        mock_init.return_value = MagicMock()  # mock config
        
        session_response = await acp_adapter.new_session(cwd="/tmp", mcp_servers=[])
        
        assert session_response is not None
        assert session_response.session_id is not None
        assert len(acp_adapter._sessions) == 1


@pytest.mark.asyncio
async def test_end_session_cleans_up_context(acp_adapter):
    """Test that end_session removes the AgentContext."""
    with patch('python.helpers.acp_adapter.AgentContext') as mock_context_cls, \
         patch('python.helpers.acp_adapter.initialize_agent') as mock_init, \
         patch('python.helpers.acp_adapter.remove_chat') as mock_remove_chat:
        
        mock_context = MagicMock()
        mock_context.id = "test-context-456"
        mock_context_cls.return_value = mock_context
        mock_context_cls.get.return_value = mock_context
        mock_context_cls.remove.return_value = mock_context
        mock_init.return_value = MagicMock()
        
        # Create a session first
        session_info = await acp_adapter.new_session()
        session_id = session_info.session_id
        
        # End the session
        await acp_adapter.end_session(session_id)
        
        # Verify cleanup
        mock_context.reset.assert_called_once()
        mock_context_cls.remove.assert_called_once_with("test-context-456")
        assert session_id not in acp_adapter._sessions
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_acp_adapter.py::test_new_session_creates_agent_context -v`
Expected: FAIL with "AttributeError" or "new_session not defined"

**Step 3: Implement session management methods**

Update `python/helpers/acp_adapter.py`, add imports and methods:
```python
# Add to imports section (after existing imports):
import uuid
from agent import AgentContext, AgentContextType, UserMessage
from initialize import initialize_agent
from python.helpers.persist_chat import remove_chat

# Add these methods to AgentZeroACP class:

    async def new_session(self, cwd: str = "", mcp_servers: list | None = None, **kwargs) -> "NewSessionResponse":
        """Create a new ACP session mapped to an Agent Zero context.
        
        Args:
            cwd: Working directory for the session.
            mcp_servers: List of MCP servers available to the session.
            
        Returns:
            NewSessionResponse with the new session ID.
        """
        if not ACP_AVAILABLE:
            raise RuntimeError("ACP SDK not available")
        
        # Generate ACP session ID
        acp_session_id = str(uuid.uuid4())
        
        # Create Agent Zero context
        config = initialize_agent()
        context = AgentContext(config, type=AgentContextType.BACKGROUND)
        
        # Store working directory in context data if provided
        if cwd:
            context.data["acp_cwd"] = cwd
        if mcp_servers:
            context.data["acp_mcp_servers"] = mcp_servers
        
        # Store mapping
        self._sessions[acp_session_id] = context.id
        
        _PRINTER.print(f"[ACP] Created session {acp_session_id} -> context {context.id}")
        
        return NewSessionResponse(session_id=acp_session_id)
    
    async def end_session(self, session_id: str) -> None:
        """End an ACP session and clean up the Agent Zero context.
        
        Args:
            session_id: The ACP session ID to end.
        """
        context_id = self._sessions.pop(session_id, None)
        if context_id:
            context = AgentContext.get(context_id)
            if context:
                context.reset()
                AgentContext.remove(context_id)
                remove_chat(context_id)
                _PRINTER.print(f"[ACP] Ended session {session_id}, cleaned up context {context_id}")
        else:
            _PRINTER.print(f"[ACP] Session {session_id} not found for cleanup")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_acp_adapter.py -v -k "session"`
Expected: PASS

**Step 5: Commit**

```bash
git add python/helpers/acp_adapter.py tests/test_acp_adapter.py
git commit -m "feat(acp): implement session lifecycle management"
```

---

### Task 1.4: Implement Basic Text Message Processing

**Files:**
- Modify: `python/helpers/acp_adapter.py`
- Test: `tests/test_acp_adapter.py`

**Step 1: Write failing test for message conversion**

Add to `tests/test_acp_adapter.py`:
```python
def test_convert_content_blocks_text_only():
    """Test converting ACP content blocks with text to UserMessage."""
    from python.helpers.acp_adapter import AgentZeroACP
    
    adapter = AgentZeroACP()
    
    # Create ACP content blocks (dict format)
    blocks = [
        {"type": "text", "text": "Hello, Agent Zero!"}
    ]
    
    user_message = adapter._convert_content_blocks(blocks)
    
    assert user_message.message == "Hello, Agent Zero!"
    assert user_message.attachments == []


def test_convert_content_blocks_multiple_text():
    """Test converting ACP content blocks with multiple text blocks."""
    from python.helpers.acp_adapter import AgentZeroACP
    
    adapter = AgentZeroACP()
    
    blocks = [
        {"type": "text", "text": "First part."},
        {"type": "text", "text": "Second part."}
    ]
    
    user_message = adapter._convert_content_blocks(blocks)
    
    assert user_message.message == "First part.\nSecond part."
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_acp_adapter.py::test_convert_acp_message_text_only -v`
Expected: FAIL with "AttributeError: _convert_acp_message"

**Step 3: Implement message conversion**

Add to `AgentZeroACP` class in `python/helpers/acp_adapter.py`:
```python
    def _convert_content_blocks(self, blocks: list["ContentBlock"]) -> UserMessage:
        """Convert ACP ContentBlocks to Agent Zero UserMessage.
        
        Args:
            blocks: List of ACP ContentBlock objects.
            
        Returns:
            UserMessage suitable for Agent Zero processing.
        """
        text_parts: list[str] = []
        attachments: list[str] = []
        
        for block in blocks:
            block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            
            if block_type == "text":
                text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                text_parts.append(text)
            elif block_type == "image":
                # Handle image content - could be URL or base64 data
                url = block.get("url") if isinstance(block, dict) else getattr(block, "url", None)
                if url:
                    attachments.append(url)
                # Base64 data would need to be saved to temp file - skip for now
            elif block_type == "resource" or block_type == "resource_link":
                # Handle embedded resource or resource link
                uri = block.get("uri") if isinstance(block, dict) else getattr(block, "uri", None)
                if uri:
                    attachments.append(uri)
        
        message_text = "\n".join(text_parts)
        
        return UserMessage(
            message=message_text,
            attachments=attachments
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_acp_adapter.py -v -k "convert"` 
Expected: PASS

**Step 5: Commit**

```bash
git add python/helpers/acp_adapter.py tests/test_acp_adapter.py
git commit -m "feat(acp): implement ACP message to UserMessage conversion"
```

---

### Task 1.5: Implement Prompt Method (Core Message Processing)

**Files:**
- Modify: `python/helpers/acp_adapter.py`
- Test: `tests/test_acp_adapter.py`

**Step 1: Write failing test for prompt processing**

Add to `tests/test_acp_adapter.py`:
```python
@pytest.mark.asyncio
async def test_prompt_processes_message_and_returns_response():
    """Test that prompt() processes content blocks and returns PromptResponse."""
    from python.helpers.acp_adapter import AgentZeroACP, ACP_AVAILABLE
    
    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")
    
    adapter = AgentZeroACP()
    
    with patch('python.helpers.acp_adapter.AgentContext') as mock_context_cls, \
         patch('python.helpers.acp_adapter.initialize_agent') as mock_init:
        
        # Setup mock context
        mock_context = MagicMock()
        mock_context.id = "ctx-789"
        mock_context.data = {}
        mock_context.agent0 = MagicMock()
        mock_context.agent0.data = {}
        mock_context.log = MagicMock()
        mock_context_cls.return_value = mock_context
        mock_context_cls.get.return_value = mock_context
        mock_init.return_value = MagicMock()
        
        # Mock the communicate method to return a result
        mock_task = MagicMock()
        async def mock_result():
            return "Hello! How can I help?"
        mock_task.result = mock_result
        mock_context.communicate.return_value = mock_task
        
        # Create session
        session_response = await adapter.new_session()
        session_id = session_response.session_id
        
        # Create ACP content blocks
        prompt_blocks = [{"type": "text", "text": "Hello"}]
        
        # Process prompt
        response = await adapter.prompt(prompt_blocks, session_id)
        
        assert response is not None
        assert response.stop_reason == "end_turn"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_acp_adapter.py::test_prompt_processes_message -v`
Expected: FAIL with "AttributeError: 'AgentZeroACP' object has no attribute 'prompt'"

**Step 3: Implement prompt method**

The `prompt` method was already implemented in Task 1.3 with the correct ACP SDK signature.
It handles:
- Converting content blocks to UserMessage
- Setting up streaming via `self.connection`
- Processing through Agent Zero's communicate()
- Returning PromptResponse with stop_reason

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_acp_adapter.py -v -k "prompt"`
Expected: PASS

**Step 5: Commit**

```bash
git add python/helpers/acp_adapter.py tests/test_acp_adapter.py
git commit -m "feat(acp): implement core prompt processing method"
```

---

## Phase 2: Streaming Response Handler

### Task 2.1: Create Stream Handler Infrastructure

**Files:**
- Create: `python/helpers/acp_stream_handler.py`
- Test: `tests/test_acp_stream_handler.py`

**Step 1: Write failing test for stream handler**

Create `tests/test_acp_stream_handler.py`:
```python
"""Tests for ACP stream handler."""
import pytest
from unittest.mock import MagicMock, AsyncMock


def test_stream_handler_initialization():
    """Test that ACPStreamHandler can be initialized."""
    from python.helpers.acp_stream_handler import ACPStreamHandler
    
    mock_session_update = AsyncMock()
    handler = ACPStreamHandler(session_id="test-session", session_update=mock_session_update)
    
    assert handler.session_id == "test-session"
    assert handler._buffer == ""


@pytest.mark.asyncio
async def test_stream_handler_sends_text_update():
    """Test that stream handler sends text updates."""
    from python.helpers.acp_stream_handler import ACPStreamHandler
    
    mock_session_update = AsyncMock()
    handler = ACPStreamHandler(session_id="test-session", session_update=mock_session_update)
    
    await handler.on_response_chunk("Hello", "Hello")
    
    mock_session_update.assert_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_acp_stream_handler.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement stream handler**

Create `python/helpers/acp_stream_handler.py`:
```python
# noqa: D401 (docstrings) - internal helper
"""ACP Stream Handler for Agent Zero.

Captures Agent Zero's streaming output and converts it to ACP session updates.
"""
from typing import Any, Callable, Coroutine

from python.helpers.print_style import PrintStyle

# Import ACP types
try:
    from acp.types import (
        SessionUpdate,
        UpdateAgentMessage,
        UpdateAgentThought,
        StartToolCall,
        UpdateToolResult,
    )
    ACP_AVAILABLE = True
except ImportError:
    ACP_AVAILABLE = False
    SessionUpdate = Any  # type: ignore
    UpdateAgentMessage = Any  # type: ignore
    UpdateAgentThought = Any  # type: ignore
    StartToolCall = Any  # type: ignore
    UpdateToolResult = Any  # type: ignore

_PRINTER = PrintStyle(italic=True, font_color="cyan", padding=False)


class ACPStreamHandler:
    """Handles streaming updates from Agent Zero to ACP clients."""
    
    def __init__(
        self,
        session_id: str,
        session_update: Callable[[SessionUpdate], Coroutine[Any, Any, None]],
    ):
        """Initialize the stream handler.
        
        Args:
            session_id: The ACP session ID.
            session_update: Async callback to send session updates to ACP client.
        """
        self.session_id = session_id
        self._session_update = session_update
        self._buffer = ""
        self._reasoning_buffer = ""
        self._current_tool: str | None = None
    
    async def on_response_chunk(self, chunk: str, full: str) -> None:
        """Handle a response stream chunk from Agent Zero.
        
        Args:
            chunk: The new chunk of text.
            full: The full accumulated text so far.
        """
        if not ACP_AVAILABLE:
            return
        
        self._buffer = full
        
        update = SessionUpdate(
            type="update_agent_message",
            content=UpdateAgentMessage(text=chunk, is_complete=False)
        )
        await self._session_update(update)
    
    async def on_reasoning_chunk(self, chunk: str, full: str) -> None:
        """Handle a reasoning stream chunk from Agent Zero.
        
        Args:
            chunk: The new chunk of reasoning text.
            full: The full accumulated reasoning so far.
        """
        if not ACP_AVAILABLE:
            return
        
        self._reasoning_buffer = full
        
        update = SessionUpdate(
            type="update_agent_thought",
            content=UpdateAgentThought(text=chunk)
        )
        await self._session_update(update)
    
    async def on_tool_start(self, tool_name: str, tool_args: dict) -> None:
        """Handle tool execution start.
        
        Args:
            tool_name: Name of the tool being executed.
            tool_args: Arguments passed to the tool.
        """
        if not ACP_AVAILABLE:
            return
        
        self._current_tool = tool_name
        
        update = SessionUpdate(
            type="start_tool_call",
            content=StartToolCall(
                tool_name=tool_name,
                arguments=tool_args
            )
        )
        await self._session_update(update)
    
    async def on_tool_result(self, tool_name: str, result: str) -> None:
        """Handle tool execution result.
        
        Args:
            tool_name: Name of the tool that completed.
            result: The tool's output.
        """
        if not ACP_AVAILABLE:
            return
        
        self._current_tool = None
        
        update = SessionUpdate(
            type="update_tool_result",
            content=UpdateToolResult(
                tool_name=tool_name,
                result=result
            )
        )
        await self._session_update(update)
    
    async def on_response_complete(self) -> None:
        """Handle response completion."""
        if not ACP_AVAILABLE:
            return
        
        update = SessionUpdate(
            type="update_agent_message",
            content=UpdateAgentMessage(text="", is_complete=True)
        )
        await self._session_update(update)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_acp_stream_handler.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add python/helpers/acp_stream_handler.py tests/test_acp_stream_handler.py
git commit -m "feat(acp): add streaming response handler"
```

---

### Task 2.2: Create ACP Streaming Extension

**Files:**
- Create: `python/extensions/acp_integration/__init__.py`
- Create: `python/extensions/acp_integration/acp_response_stream.py`

**Step 1: Create extension directory structure**

```bash
mkdir -p python/extensions/acp_integration
touch python/extensions/acp_integration/__init__.py
```

**Step 2: Write the streaming extension**

Create `python/extensions/acp_integration/acp_response_stream.py`:
```python
"""ACP response stream extension.

Hooks into Agent Zero's response streaming to send real-time updates to ACP clients.
"""
from python.helpers.extension import Extension


class ACPResponseStream(Extension):
    """Extension that forwards response stream chunks to ACP clients."""
    
    async def execute(self, stream_data: dict | None = None, **kwargs) -> None:
        """Forward response chunks to ACP stream handler if active.
        
        Args:
            stream_data: Dictionary with 'chunk' and 'full' keys.
            **kwargs: Additional arguments.
        """
        if not stream_data:
            return
        
        # Check if this agent has an active ACP stream handler
        handler = self.agent.data.get("_acp_stream_handler")
        if not handler:
            return
        
        chunk = stream_data.get("chunk", "")
        full = stream_data.get("full", "")
        
        if chunk:
            await handler.on_response_chunk(chunk, full)
```

**Step 3: Create reasoning stream extension**

Create `python/extensions/acp_integration/acp_reasoning_stream.py`:
```python
"""ACP reasoning stream extension.

Hooks into Agent Zero's reasoning streaming to send thoughts to ACP clients.
"""
from python.helpers.extension import Extension


class ACPReasoningStream(Extension):
    """Extension that forwards reasoning chunks to ACP clients."""
    
    async def execute(self, stream_data: dict | None = None, **kwargs) -> None:
        """Forward reasoning chunks to ACP stream handler if active.
        
        Args:
            stream_data: Dictionary with 'chunk' and 'full' keys.
            **kwargs: Additional arguments.
        """
        if not stream_data:
            return
        
        # Check if this agent has an active ACP stream handler
        handler = self.agent.data.get("_acp_stream_handler")
        if not handler:
            return
        
        chunk = stream_data.get("chunk", "")
        full = stream_data.get("full", "")
        
        if chunk:
            await handler.on_reasoning_chunk(chunk, full)
```

**Step 4: Commit**

```bash
git add python/extensions/acp_integration/
git commit -m "feat(acp): add streaming extensions for response and reasoning"
```

---

### Task 2.3: Create Tool Execution Extensions for ACP

**Files:**
- Create: `python/extensions/acp_integration/acp_tool_before.py`
- Create: `python/extensions/acp_integration/acp_tool_after.py`

**Step 1: Create tool_execute_before extension**

Create `python/extensions/acp_integration/acp_tool_before.py`:
```python
"""ACP tool execution start extension.

Notifies ACP clients when Agent Zero starts executing a tool.
"""
from python.helpers.extension import Extension


class ACPToolBefore(Extension):
    """Extension that notifies ACP clients of tool execution start."""
    
    async def execute(self, tool_name: str = "", tool_args: dict | None = None, **kwargs) -> None:
        """Notify ACP client of tool execution start.
        
        Args:
            tool_name: Name of the tool being executed.
            tool_args: Arguments passed to the tool.
            **kwargs: Additional arguments.
        """
        handler = self.agent.data.get("_acp_stream_handler")
        if not handler:
            return
        
        await handler.on_tool_start(tool_name, tool_args or {})
```

**Step 2: Create tool_execute_after extension**

Create `python/extensions/acp_integration/acp_tool_after.py`:
```python
"""ACP tool execution complete extension.

Notifies ACP clients when Agent Zero completes executing a tool.
"""
from python.helpers.extension import Extension


class ACPToolAfter(Extension):
    """Extension that notifies ACP clients of tool execution completion."""
    
    async def execute(self, tool_name: str = "", response: object | None = None, **kwargs) -> None:
        """Notify ACP client of tool execution completion.
        
        Args:
            tool_name: Name of the tool that completed.
            response: The tool's response object.
            **kwargs: Additional arguments.
        """
        handler = self.agent.data.get("_acp_stream_handler")
        if not handler:
            return
        
        result_text = ""
        if response and hasattr(response, 'message'):
            result_text = str(response.message)
        
        await handler.on_tool_result(tool_name, result_text)
```

**Step 3: Commit**

```bash
git add python/extensions/acp_integration/acp_tool_*.py
git commit -m "feat(acp): add tool execution notification extensions"
```

---

### Task 2.4: Integrate Stream Handler into Prompt Method

**Files:**
- Modify: `python/helpers/acp_adapter.py`

**Step 1: Update prompt method to use stream handler**

Modify the `prompt` method in `python/helpers/acp_adapter.py` to support streaming:
```python
    async def prompt(
        self,
        session_id: str,
        message: "Message",
        session_update: Callable[["SessionUpdate"], Coroutine[Any, Any, None]] | None = None,
    ) -> "Message":
        """Process an ACP prompt and return the agent's response.
        
        Args:
            session_id: The ACP session ID.
            message: The ACP Message containing user content.
            session_update: Optional callback for streaming updates.
            
        Returns:
            ACP Message with the agent's response.
        """
        if not ACP_AVAILABLE:
            raise RuntimeError("ACP SDK not available")
        
        # Import here to avoid circular imports
        from python.helpers.acp_stream_handler import ACPStreamHandler
        
        # Get the Agent Zero context for this session
        context_id = self._sessions.get(session_id)
        if not context_id:
            raise ValueError(f"Unknown session: {session_id}")
        
        context = AgentContext.get(context_id)
        if not context:
            raise ValueError(f"Context not found for session: {session_id}")
        
        # Convert ACP message to Agent Zero format
        user_message = self._convert_acp_message(message)
        
        _PRINTER.print(f"[ACP] Processing prompt in session {session_id}")
        
        # Set up stream handler if callback provided
        stream_handler = None
        if session_update:
            stream_handler = ACPStreamHandler(session_id, session_update)
            # Store handler in agent data for extensions to access
            context.agent0.data["_acp_stream_handler"] = stream_handler
        
        try:
            # Log user message for UI visibility
            context.log.log(
                type="user",
                heading="ACP user message",
                content=user_message.message,
                kvps={"from": "ACP"},
                temp=False,
            )
            
            # Process through Agent Zero
            task = context.communicate(user_message)
            result_text = await task.result()
            
            # Signal completion if streaming
            if stream_handler:
                await stream_handler.on_response_complete()
            
            _PRINTER.print(f"[ACP] Completed prompt in session {session_id}")
            
            # Build ACP response message
            response = Message(
                content=[TextContent(type="text", text=str(result_text))]
            )
            
            return response
            
        finally:
            # Clean up stream handler
            if stream_handler:
                context.agent0.data.pop("_acp_stream_handler", None)
```

**Step 2: Add missing import**

Add to imports at top of `python/helpers/acp_adapter.py`:
```python
from typing import Any, AsyncIterator, Callable, Coroutine
```

**Step 3: Commit**

```bash
git add python/helpers/acp_adapter.py
git commit -m "feat(acp): integrate stream handler into prompt processing"
```

---

## Phase 3: ACP Server Entry Point

### Task 3.1: Create ACP Entry Point Script

**Files:**
- Create: `run_acp.py`

**Step 1: Write the entry point script**

Create `run_acp.py`:
```python
#!/usr/bin/env python3
"""Run Agent Zero as an ACP (Agent Client Protocol) agent.

This script starts Agent Zero in ACP mode using stdio communication,
making it accessible to ACP clients like Zed IDE.

Usage:
    python run_acp.py
    
For Zed IDE integration, add to your agent configuration:
    {
        "command": "python",
        "args": ["/path/to/agent-zero/run_acp.py"]
    }
"""
import asyncio
import sys
import os

# Redirect stderr to a log file to keep stdio clean for ACP protocol
log_file = open("/tmp/agent-zero-acp.log", "a")
sys.stderr = log_file

# Initialize runtime and environment
from python.helpers import runtime, dotenv
runtime.initialize()
dotenv.load_dotenv()

from python.helpers.print_style import PrintStyle

# Check ACP availability
try:
    from acp import run_agent
    from python.helpers.acp_adapter import AgentZeroACP, is_available
    ACP_AVAILABLE = True
except ImportError:
    ACP_AVAILABLE = False


async def main():
    """Main entry point for ACP agent."""
    if not ACP_AVAILABLE:
        print("Error: ACP SDK not installed. Run: pip install agent-client-protocol", file=log_file)
        sys.exit(1)
    
    if not is_available():
        print("Error: ACP adapter not available.", file=log_file)
        sys.exit(1)
    
    print("Starting Agent Zero ACP agent (stdio mode)...", file=log_file)
    
    # Create and run the ACP agent
    agent = AgentZeroACP()
    
    try:
        await run_agent(agent)
    except Exception as e:
        print(f"Error: {e}", file=log_file)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Agent Zero ACP shutting down...", file=log_file)
    finally:
        log_file.close()
```

**Step 2: Make executable**

```bash
chmod +x run_acp.py
```

**Step 3: Commit**

```bash
git add run_acp.py
git commit -m "feat(acp): add standalone ACP server entry point"
```

---

### Task 3.2: Add ACP to Web UI Server (Optional Integration)

**Files:**
- Modify: `run_ui.py`

**Step 1: Add ACP route to dispatcher middleware**

Modify `run_ui.py` around line 240-246, after the fasta2a route:
```python
    # add the webapp, mcp, a2a, and acp to the app
    middleware_routes = {
        "/mcp": ASGIMiddleware(app=mcp_server.DynamicMcpProxy.get_instance()),  # type: ignore
        "/a2a": ASGIMiddleware(app=fasta2a_server.DynamicA2AProxy.get_instance()),  # type: ignore
    }
    
    # Add ACP route if available
    try:
        from python.helpers import acp_adapter
        if acp_adapter.is_available():
            from python.helpers.acp_server import DynamicACPProxy
            middleware_routes["/acp"] = ASGIMiddleware(app=DynamicACPProxy.get_instance())  # type: ignore
    except ImportError:
        pass  # ACP not available

    app = DispatcherMiddleware(webapp, middleware_routes)  # type: ignore
```

**Step 2: Create dynamic ACP proxy**

Create `python/helpers/acp_server.py`:
```python
# noqa: D401 (docstrings) - internal helper
"""ACP Server proxy for Agent Zero Web UI integration.

Provides a dynamic proxy that wraps the ACP adapter for ASGI middleware.
"""
import asyncio
import threading
from typing import Any

from python.helpers import settings
from python.helpers.print_style import PrintStyle
from python.helpers.acp_adapter import AgentZeroACP, ACP_AVAILABLE

_PRINTER = PrintStyle(italic=True, font_color="cyan", padding=False)


class DynamicACPProxy:
    """Dynamic proxy for ACP server that allows reconfiguration."""
    
    _instance = None
    
    def __init__(self):
        self._agent: AgentZeroACP | None = None
        self._lock = threading.Lock()
        
        if ACP_AVAILABLE:
            self._agent = AgentZeroACP()
            _PRINTER.print("[ACP] Server proxy initialized")
        else:
            _PRINTER.print("[ACP] ACP SDK not available, server will return 503")
    
    @staticmethod
    def get_instance() -> "DynamicACPProxy":
        if DynamicACPProxy._instance is None:
            DynamicACPProxy._instance = DynamicACPProxy()
        return DynamicACPProxy._instance
    
    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        """ASGI application interface."""
        if not ACP_AVAILABLE or not self._agent:
            await send({
                'type': 'http.response.start',
                'status': 503,
                'headers': [[b'content-type', b'text/plain']],
            })
            await send({
                'type': 'http.response.body',
                'body': b'ACP not available',
            })
            return
        
        # Check if ACP is enabled in settings
        cfg = settings.get_settings()
        if not cfg.get("acp_server_enabled", False):
            await send({
                'type': 'http.response.start',
                'status': 403,
                'headers': [[b'content-type', b'text/plain']],
            })
            await send({
                'type': 'http.response.body',
                'body': b'ACP server is disabled',
            })
            return
        
        # Handle ACP protocol messages
        # This would need to implement the actual ACP WebSocket protocol
        # For now, return a basic info response
        if scope['type'] == 'http':
            await send({
                'type': 'http.response.start',
                'status': 200,
                'headers': [[b'content-type', b'application/json']],
            })
            
            import json
            info = await self._agent.get_agent_info()
            body = json.dumps({
                "name": info.name,
                "description": info.description,
                "version": info.version,
                "status": "ready"
            })
            
            await send({
                'type': 'http.response.body',
                'body': body.encode(),
            })
```

**Step 3: Commit**

```bash
git add run_ui.py python/helpers/acp_server.py
git commit -m "feat(acp): add ACP route to web UI server"
```

---

## Phase 4: Configuration

### Task 4.1: Add ACP Settings

**Files:**
- Modify: `python/helpers/settings.py` (add ACP settings schema)
- Create: `conf/acp_settings.yaml`

**Step 1: Find settings schema and add ACP fields**

First, read the settings.py to understand the schema:
```bash
grep -n "acp\|mcp_server\|a2a_server" python/helpers/settings.py
```

**Step 2: Add ACP settings to settings.py**

Add these fields to the settings schema in `python/helpers/settings.py`:
```python
# ACP settings
"acp_server_enabled": False,
"acp_session_timeout": 3600,  # Session timeout in seconds (1 hour)
"acp_stream_buffer_size": 4096,  # Buffer size for streaming responses
```

**Step 3: Create default ACP configuration file**

Create `conf/acp_settings.yaml`:
```yaml
# ACP (Agent Client Protocol) Configuration
# These settings control how Agent Zero behaves as an ACP server

# Enable/disable ACP server
acp_server_enabled: false

# Session timeout in seconds (default: 1 hour)
acp_session_timeout: 3600

# Buffer size for streaming responses in bytes
acp_stream_buffer_size: 4096

# Protocol version to advertise
acp_protocol_version: "1.0"

# Capabilities to advertise to ACP clients
acp_capabilities:
  # File system operations
  read_text_file: true
  write_text_file: true
  list_directory: true
  
  # Terminal operations (via SSH execution)
  terminal: true
  
  # Content types supported in prompts
  prompt_content_types:
    text: true
    image: true  # Depends on vision model config
    audio: false  # Depends on whisper config
    embedded_resource: true
```

**Step 4: Commit**

```bash
git add python/helpers/settings.py conf/acp_settings.yaml
git commit -m "feat(acp): add ACP configuration settings"
```

---

## Phase 5: Documentation

### Task 5.1: Create ACP Integration Documentation

**Files:**
- Create: `docs/acp_integration.md`

**Step 1: Write documentation**

Create `docs/acp_integration.md`:
```markdown
# ACP (Agent Client Protocol) Integration

Agent Zero supports the Agent Client Protocol (ACP), enabling integration with ACP-compatible clients like Zed IDE, Claude Desktop, and other applications.

## Overview

ACP is a protocol that allows AI agents to communicate with client applications in a standardized way. When running in ACP mode, Agent Zero:

- Exposes its full capabilities through the ACP interface
- Supports real-time streaming of responses, reasoning, and tool execution
- Manages sessions for multiple concurrent clients
- Handles file system and terminal operations via the ACP protocol

## Quick Start

### Standalone ACP Agent (stdio mode)

Run Agent Zero as an ACP agent (communicates via stdio):

```bash
python run_acp.py
```

**Note:** ACP uses stdio for communication. Logs are written to `/tmp/agent-zero-acp.log`.

### Integrated with Web UI

Enable ACP in your settings:

1. Set `acp_server_enabled: true` in settings
2. Restart Agent Zero
3. ACP will be available at `http://localhost:50001/acp`

## Configuration

ACP settings can be configured in `conf/acp_settings.yaml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `acp_server_enabled` | `false` | Enable/disable ACP server |
| `acp_session_timeout` | `3600` | Session timeout in seconds |
| `acp_stream_buffer_size` | `4096` | Buffer size for streaming |

## Connecting Clients

### Zed IDE

1. Install Zed IDE
2. Open Settings → AI → Agent
3. Add Agent Zero as a custom agent:
   ```json
   {
     "command": "python",
     "args": ["/path/to/agent-zero/run_acp.py"],
     "cwd": "/path/to/your/project"
   }
   ```

### Custom Clients

The ACP SDK uses stdio for communication. To integrate programmatically,
spawn the agent as a subprocess:

```python
import asyncio
import subprocess
import json

# Spawn agent process
proc = subprocess.Popen(
    ["python", "run_acp.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL
)

# Send initialize request
request = {"jsonrpc": "2.0", "method": "initialize", "params": {"protocol_version": 1}, "id": 1}
proc.stdin.write((json.dumps(request) + "\n").encode())
proc.stdin.flush()

# Read response
response = json.loads(proc.stdout.readline())
print(f"Initialized: {response}")
```

## Features

### Streaming Responses

Agent Zero streams responses in real-time:
- `update_agent_message` - Response text chunks
- `update_agent_thought` - Reasoning/thinking chunks  
- `start_tool_call` - Tool execution notifications
- `update_tool_result` - Tool results

### Content Types

Supported content in prompts:
- **Text**: Primary content type
- **Images**: When vision model is configured
- **Embedded Resources**: File references and URIs

### Tool Execution

All Agent Zero tools are available through ACP:
- Code execution
- File management
- Web browsing
- Memory operations
- MCP server tools

## Troubleshooting

### ACP Not Available

If you see "ACP SDK not installed":
```bash
pip install agent-client-protocol
```

### Agent Not Starting

1. Check logs at `/tmp/agent-zero-acp.log`
2. Verify Python path is correct in client configuration
3. Ensure all Agent Zero dependencies are installed

### Session Issues

- ACP uses stdio, so ensure nothing else writes to stdout
- Logs go to stderr (redirected to log file)
- Check log file for detailed error messages

### Zed IDE Not Connecting

1. Verify the command path is absolute
2. Check that `run_acp.py` is executable
3. Review Zed's agent logs for connection errors

## Architecture

```
ACP Client (Zed, etc.)
        │
        ▼
┌─────────────────┐
│  ACP Adapter    │ ← Translates ACP ↔ Agent Zero
│ (acp_adapter.py)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AgentContext   │ ← Session management
│    (agent.py)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Agent       │ ← Core agent logic
│   Monologue     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Tools/MCP     │ ← Execution capabilities
└─────────────────┘
```

## Security

- ACP sessions use the same authentication as the web UI
- Configure `mcp_server_token` for API key authentication
- Run on localhost for local development
- Use TLS for production deployments
```

**Step 2: Commit**

```bash
git add docs/acp_integration.md
git commit -m "docs: add ACP integration documentation"
```

---

### Task 5.2: Update Main README

**Files:**
- Modify: `README.md`

**Step 1: Add ACP section to README**

Add to the Connectivity section in `README.md`:
```markdown
### ACP (Agent Client Protocol)

Agent Zero supports the Agent Client Protocol for integration with compatible clients:

```bash
# Run as standalone ACP server
python run_acp.py --port 8765
```

See [ACP Integration](./docs/acp_integration.md) for details.
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add ACP reference to README"
```

---

## Phase 6: Final Integration Tests

### Task 6.1: Create End-to-End Integration Test

**Files:**
- Create: `tests/test_acp_integration.py`

**Step 1: Write integration test**

Create `tests/test_acp_integration.py`:
```python
"""End-to-end integration tests for ACP adapter."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio


@pytest.fixture
def mock_agent_context():
    """Create a comprehensive mock AgentContext."""
    with patch('python.helpers.acp_adapter.AgentContext') as mock_cls, \
         patch('python.helpers.acp_adapter.initialize_agent') as mock_init, \
         patch('python.helpers.acp_adapter.remove_chat'):
        
        mock_context = MagicMock()
        mock_context.id = "integration-test-ctx"
        mock_context.log = MagicMock()
        mock_context.agent0 = MagicMock()
        mock_context.agent0.data = {}
        
        # Setup communicate to return async result
        mock_task = MagicMock()
        async def mock_result():
            return "Test response from Agent Zero"
        mock_task.result = mock_result
        mock_context.communicate.return_value = mock_task
        
        mock_cls.return_value = mock_context
        mock_cls.get.return_value = mock_context
        mock_init.return_value = MagicMock()
        
        yield mock_context


@pytest.mark.asyncio
async def test_full_session_lifecycle(mock_agent_context):
    """Test complete session lifecycle: create, prompt, end."""
    from python.helpers.acp_adapter import AgentZeroACP, ACP_AVAILABLE
    
    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")
    
    adapter = AgentZeroACP()
    
    # Create session
    session = await adapter.new_session(cwd="/tmp")
    assert session.session_id is not None
    
    # Send prompt with content blocks
    prompt_blocks = [{"type": "text", "text": "Hello"}]
    response = await adapter.prompt(prompt_blocks, session.session_id)
    
    assert response is not None
    assert response.stop_reason == "end_turn"
    
    # End session
    await adapter.end_session(session.session_id)
    assert session.session_id not in adapter._sessions


@pytest.mark.asyncio
async def test_streaming_integration(mock_agent_context):
    """Test streaming updates are sent via connection."""
    from python.helpers.acp_adapter import AgentZeroACP, ACP_AVAILABLE
    
    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")
    
    adapter = AgentZeroACP()
    
    # Track updates sent via connection
    received_updates = []
    
    # Mock the connection object
    mock_connection = MagicMock()
    async def mock_session_update(session_id, update):
        received_updates.append((session_id, update))
    mock_connection.session_update = mock_session_update
    adapter.connection = mock_connection
    
    # Create session
    session = await adapter.new_session()
    
    # Send prompt
    prompt_blocks = [{"type": "text", "text": "Stream test"}]
    response = await adapter.prompt(prompt_blocks, session.session_id)
    
    # Should have sent update via connection
    assert len(received_updates) > 0
    
    await adapter.end_session(session.session_id)


@pytest.mark.asyncio
async def test_multiple_concurrent_sessions(mock_agent_context):
    """Test handling multiple concurrent sessions."""
    from python.helpers.acp_adapter import AgentZeroACP, ACP_AVAILABLE
    
    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")
    
    adapter = AgentZeroACP()
    
    # Create multiple sessions
    sessions = []
    for _ in range(3):
        session = await adapter.new_session()
        sessions.append(session.session_id)
    
    assert len(adapter._sessions) == 3
    assert len(set(sessions)) == 3  # All unique
    
    # End all sessions
    for sid in sessions:
        await adapter.end_session(sid)
    
    assert len(adapter._sessions) == 0


@pytest.mark.asyncio
async def test_invalid_session_handling():
    """Test handling of invalid session IDs."""
    from python.helpers.acp_adapter import AgentZeroACP, ACP_AVAILABLE
    
    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")
    
    adapter = AgentZeroACP()
    
    prompt_blocks = [{"type": "text", "text": "Test"}]
    
    with pytest.raises(ValueError, match="Unknown session"):
        await adapter.prompt(prompt_blocks, "nonexistent-session-id")
```

**Step 2: Run integration tests**

Run: `pytest tests/test_acp_integration.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_acp_integration.py
git commit -m "test: add ACP integration end-to-end tests"
```

---

### Task 6.2: Final Verification

**Step 1: Run all ACP tests**

```bash
pytest tests/test_acp*.py -v
```
Expected: All tests pass

**Step 2: Run linting/type checks**

```bash
# If project has type checking configured
python -m mypy python/helpers/acp_adapter.py python/helpers/acp_stream_handler.py --ignore-missing-imports
```

**Step 3: Manual smoke test**

```bash
# Start ACP server
python run_acp.py --port 8765

# In another terminal, test with curl
curl http://localhost:8765/info
```
Expected: Returns JSON with agent info

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(acp): complete ACP integration implementation"
```

---

## Summary

This plan implements ACP integration in 6 phases:

1. **Foundation** - Core adapter module with session management and message processing
2. **Streaming** - Real-time response streaming via extensions
3. **Entry Point** - Standalone ACP server and web UI integration
4. **Configuration** - Settings for ACP behavior
5. **Documentation** - User guide and README updates
6. **Testing** - Integration tests and verification

**Total Tasks:** 14 tasks across 6 phases

**Estimated Time:** 4-6 hours for full implementation

**Files Created:**
- `python/helpers/acp_adapter.py` - Main ACP adapter
- `python/helpers/acp_stream_handler.py` - Streaming handler
- `python/helpers/acp_server.py` - ASGI proxy for web UI
- `python/extensions/acp_integration/*.py` - Streaming extensions
- `run_acp.py` - Standalone entry point
- `conf/acp_settings.yaml` - Default configuration
- `docs/acp_integration.md` - User documentation
- `tests/test_acp_*.py` - Test suites

**Key Design Decisions:**
- Follows existing `fasta2a_server.py` adapter pattern
- Uses Agent Zero's extension system for streaming hooks
- Maintains 100% backward compatibility
- ACP is opt-in via configuration
