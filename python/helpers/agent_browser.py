"""
Agent Browser CLI Wrapper

Provides a Python interface to the agent-browser CLI tool for browser automation.
Uses subprocess to execute commands and parse JSON output.
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional
from python.helpers import files
from python.helpers.print_style import PrintStyle


@dataclass
class AgentBrowserConfig:
    """Configuration for AgentBrowser instance."""
    session_name: str = "default"
    executable_path: Optional[str] = None
    stream_port: Optional[int] = None
    headed: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720


@dataclass
class SnapshotRef:
    """Represents an element reference from a snapshot."""
    ref: str
    role: str
    name: str
    level: Optional[int] = None


@dataclass
class AgentBrowserResult:
    """Result from an agent-browser command."""
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    raw_output: str = ""

    @classmethod
    def from_json(cls, output: str) -> "AgentBrowserResult":
        """Parse JSON output from agent-browser --json flag."""
        try:
            parsed = json.loads(output)
            return cls(
                success=parsed.get("success", False),
                data=parsed.get("data", {}),
                error=parsed.get("error"),
                raw_output=output
            )
        except json.JSONDecodeError as e:
            return cls(
                success=False,
                error=f"Failed to parse JSON: {e}",
                raw_output=output
            )

    @classmethod
    def from_error(cls, error: str) -> "AgentBrowserResult":
        """Create an error result."""
        return cls(success=False, error=error)


class AgentBrowser:
    """
    Python wrapper for agent-browser CLI.
    
    Provides async methods for browser automation using the agent-browser
    command-line tool with JSON output for structured responses.
    
    Usage:
        browser = AgentBrowser(config=AgentBrowserConfig(session_name="my-session"))
        await browser.open("https://example.com")
        snapshot = await browser.snapshot(interactive=True)
        await browser.click("@e2")
        await browser.close()
    """

    def __init__(self, config: Optional[AgentBrowserConfig] = None):
        self.config = config or AgentBrowserConfig()
        self._refs: dict[str, SnapshotRef] = {}
        self._current_url: Optional[str] = None
        self._is_open: bool = False

    async def execute(self, *args: str, use_json: bool = True) -> AgentBrowserResult:
        """
        Execute an agent-browser command.
        
        Args:
            *args: Command arguments (e.g., "open", "https://example.com")
            use_json: Whether to add --json flag for structured output
            
        Returns:
            AgentBrowserResult with parsed output
        """
        cmd = ["agent-browser"]
        
        # Add session flag
        if self.config.session_name != "default":
            cmd.extend(["--session", self.config.session_name])
        
        # Add executable path if specified (for Docker Chromium reuse)
        if self.config.executable_path:
            cmd.extend(["--executable-path", self.config.executable_path])
        
        # Add the command arguments
        cmd.extend(args)
        
        # Add JSON output flag for parsing
        if use_json:
            cmd.append("--json")
        
        # Set up environment for streaming if configured
        env = os.environ.copy()
        if self.config.stream_port:
            env["AGENT_BROWSER_STREAM_PORT"] = str(self.config.stream_port)
        
        try:
            PrintStyle().hint(f"agent-browser: {' '.join(args[:3])}...")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60.0  # 60 second timeout per command
            )
            
            output = stdout.decode("utf-8").strip()
            error_output = stderr.decode("utf-8").strip()
            
            if process.returncode != 0:
                return AgentBrowserResult.from_error(
                    error_output or f"Command failed with code {process.returncode}"
                )
            
            if use_json and output:
                return AgentBrowserResult.from_json(output)
            else:
                return AgentBrowserResult(success=True, raw_output=output)
                
        except asyncio.TimeoutError:
            return AgentBrowserResult.from_error("Command timed out after 60 seconds")
        except FileNotFoundError:
            return AgentBrowserResult.from_error(
                "agent-browser not found. Install with: npm install -g agent-browser"
            )
        except Exception as e:
            return AgentBrowserResult.from_error(f"Execution error: {str(e)}")

    async def open(self, url: str, headed: bool = False) -> AgentBrowserResult:
        """
        Navigate to a URL.
        
        Args:
            url: The URL to navigate to
            headed: Whether to show the browser window (for user intervention)
            
        Returns:
            AgentBrowserResult
        """
        args = ["open", url]
        if headed or self.config.headed:
            args.append("--headed")
        
        result = await self.execute(*args)
        if result.success:
            self._current_url = url
            self._is_open = True
        return result

    async def snapshot(self, interactive: bool = True, compact: bool = True, 
                       depth: Optional[int] = None, selector: Optional[str] = None) -> AgentBrowserResult:
        """
        Get accessibility tree snapshot with element refs.
        
        Args:
            interactive: Only include interactive elements (buttons, links, inputs)
            compact: Remove empty structural elements
            depth: Limit tree depth
            selector: Scope to CSS selector
            
        Returns:
            AgentBrowserResult with snapshot data and refs
        """
        args = ["snapshot"]
        if interactive:
            args.append("-i")
        if compact:
            args.append("-c")
        if depth:
            args.extend(["-d", str(depth)])
        if selector:
            args.extend(["-s", selector])
        
        result = await self.execute(*args)
        
        # Parse refs from the result if successful
        if result.success and "refs" in result.data:
            self._refs = {}
            for ref_id, ref_data in result.data["refs"].items():
                self._refs[ref_id] = SnapshotRef(
                    ref=ref_id,
                    role=ref_data.get("role", ""),
                    name=ref_data.get("name", ""),
                    level=ref_data.get("level")
                )
        
        return result

    async def click(self, selector: str) -> AgentBrowserResult:
        """
        Click an element by ref or CSS selector.
        
        Args:
            selector: Element ref (e.g., "@e2") or CSS selector
            
        Returns:
            AgentBrowserResult
        """
        return await self.execute("click", selector)

    async def fill(self, selector: str, text: str) -> AgentBrowserResult:
        """
        Clear and fill an input element.
        
        Args:
            selector: Element ref (e.g., "@e3") or CSS selector
            text: Text to fill
            
        Returns:
            AgentBrowserResult
        """
        return await self.execute("fill", selector, text)

    async def type_text(self, selector: str, text: str) -> AgentBrowserResult:
        """
        Type into an element (without clearing first).
        
        Args:
            selector: Element ref or CSS selector
            text: Text to type
            
        Returns:
            AgentBrowserResult
        """
        return await self.execute("type", selector, text)

    async def press(self, key: str) -> AgentBrowserResult:
        """
        Press a key (Enter, Tab, Escape, etc.).
        
        Args:
            key: Key name (e.g., "Enter", "Tab", "Control+a")
            
        Returns:
            AgentBrowserResult
        """
        return await self.execute("press", key)

    async def hover(self, selector: str) -> AgentBrowserResult:
        """
        Hover over an element.
        
        Args:
            selector: Element ref or CSS selector
            
        Returns:
            AgentBrowserResult
        """
        return await self.execute("hover", selector)

    async def select(self, selector: str, value: str) -> AgentBrowserResult:
        """
        Select a dropdown option.
        
        Args:
            selector: Element ref or CSS selector
            value: Option value to select
            
        Returns:
            AgentBrowserResult
        """
        return await self.execute("select", selector, value)

    async def scroll(self, direction: str = "down", pixels: int = 500) -> AgentBrowserResult:
        """
        Scroll the page.
        
        Args:
            direction: "up", "down", "left", or "right"
            pixels: Number of pixels to scroll
            
        Returns:
            AgentBrowserResult
        """
        return await self.execute("scroll", direction, str(pixels))

    async def screenshot(self, path: Optional[str] = None, full_page: bool = False) -> AgentBrowserResult:
        """
        Take a screenshot.
        
        Args:
            path: Optional file path to save (returns base64 if not provided)
            full_page: Whether to capture full page
            
        Returns:
            AgentBrowserResult with screenshot data or path
        """
        args = ["screenshot"]
        if path:
            # Ensure directory exists
            files.make_dirs(path)
            args.append(path)
        if full_page:
            args.append("--full")
        
        return await self.execute(*args, use_json=not path)

    async def get_text(self, selector: str) -> AgentBrowserResult:
        """
        Get text content of an element.
        
        Args:
            selector: Element ref or CSS selector
            
        Returns:
            AgentBrowserResult with text content
        """
        return await self.execute("get", "text", selector)

    async def get_url(self) -> AgentBrowserResult:
        """Get current page URL."""
        result = await self.execute("get", "url")
        if result.success:
            self._current_url = result.data.get("url", result.raw_output)
        return result

    async def get_title(self) -> AgentBrowserResult:
        """Get current page title."""
        return await self.execute("get", "title")

    async def is_visible(self, selector: str) -> AgentBrowserResult:
        """Check if an element is visible."""
        return await self.execute("is", "visible", selector)

    async def wait(self, selector_or_ms: str, 
                   text: Optional[str] = None,
                   url_pattern: Optional[str] = None) -> AgentBrowserResult:
        """
        Wait for element, text, URL, or time.
        
        Args:
            selector_or_ms: CSS selector or milliseconds to wait
            text: Wait for text to appear
            url_pattern: Wait for URL pattern
            
        Returns:
            AgentBrowserResult
        """
        args = ["wait"]
        if text:
            args.extend(["--text", text])
        elif url_pattern:
            args.extend(["--url", url_pattern])
        else:
            args.append(selector_or_ms)
        
        return await self.execute(*args)

    async def back(self) -> AgentBrowserResult:
        """Navigate back in history."""
        return await self.execute("back")

    async def forward(self) -> AgentBrowserResult:
        """Navigate forward in history."""
        return await self.execute("forward")

    async def reload(self) -> AgentBrowserResult:
        """Reload the current page."""
        return await self.execute("reload")

    async def eval_js(self, js_code: str) -> AgentBrowserResult:
        """
        Execute JavaScript in the page.
        
        Args:
            js_code: JavaScript code to execute
            
        Returns:
            AgentBrowserResult with evaluation result
        """
        return await self.execute("eval", js_code)

    async def close(self) -> AgentBrowserResult:
        """Close the browser session."""
        result = await self.execute("close", use_json=False)
        self._is_open = False
        self._current_url = None
        self._refs = {}
        return result

    # Properties
    @property
    def refs(self) -> dict[str, SnapshotRef]:
        """Get the current element refs from the last snapshot."""
        return self._refs

    @property
    def current_url(self) -> Optional[str]:
        """Get the current URL if known."""
        return self._current_url

    @property
    def is_open(self) -> bool:
        """Check if a browser session is active."""
        return self._is_open

    def get_ref_by_name(self, name: str) -> Optional[str]:
        """
        Find a ref by its accessible name (case-insensitive partial match).
        
        Args:
            name: Text to search for in element names
            
        Returns:
            Ref string (e.g., "@e2") or None if not found
        """
        name_lower = name.lower()
        for ref_id, ref in self._refs.items():
            if name_lower in ref.name.lower():
                return f"@{ref_id}"
        return None

    def get_ref_by_role(self, role: str) -> list[str]:
        """
        Find refs by their ARIA role.
        
        Args:
            role: Role to search for (e.g., "button", "textbox", "link")
            
        Returns:
            List of ref strings
        """
        return [f"@{ref_id}" for ref_id, ref in self._refs.items() 
                if ref.role.lower() == role.lower()]
