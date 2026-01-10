"""
Canvas - Visual Workspace for Agent Zero

A visual workspace system that allows agents to write HTML/CSS/JS files,
view them in a real browser, query the DOM, and capture screenshots.

Inspired by github.com/steipete/canvas (Go) - ported to Python for Agent Zero.
"""

import asyncio
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial

from python.helpers import files
from python.helpers.print_style import PrintStyle
from python.helpers.playwright import ensure_playwright_binary

# Optional imports for browser control
try:
    from playwright.async_api import async_playwright, Browser, Page, Playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@dataclass
class CanvasConfig:
    """Configuration for Canvas workspace."""
    headless: bool = True
    auto_reload: bool = True
    window_width: int = 1280
    window_height: int = 720
    reload_debounce_ms: int = 300


@dataclass
class CanvasState:
    """Runtime state for a Canvas instance."""
    workspace_dir: str = ""
    server_url: str = ""
    server_port: int = 0
    server_thread: Optional[threading.Thread] = None
    http_server: Optional[HTTPServer] = None
    playwright: Optional[Any] = None  # Playwright instance
    browser: Optional[Any] = None  # Browser instance
    page: Optional[Any] = None  # Page instance
    watcher_task: Optional[asyncio.Task] = None
    is_running: bool = False
    last_reload_time: float = 0


class SilentHTTPRequestHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves files silently (no logging)."""

    def __init__(self, *args, directory: str = None, welcome_html: str = None, **kwargs):
        self.welcome_html = welcome_html or DEFAULT_WELCOME_HTML
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """Handle GET requests with welcome page fallback."""
        # Normalize path
        path = self.path.split('?')[0].split('#')[0]

        # Check for index.html at root
        if path == '/' or path == '':
            index_path = Path(self.directory) / 'index.html'
            index_htm_path = Path(self.directory) / 'index.htm'

            if not index_path.exists() and not index_htm_path.exists():
                # Serve welcome page
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(self.welcome_html.encode('utf-8'))
                return

        # Default behavior for other paths
        return super().do_GET()

    def end_headers(self):
        """Add CORS headers for local development."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()


DEFAULT_WELCOME_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Canvas Workspace</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e8e8e8;
        }
        .container {
            text-align: center;
            padding: 40px;
            max-width: 600px;
        }
        .logo {
            width: 80px;
            height: 80px;
            margin-bottom: 24px;
            opacity: 0.9;
        }
        h1 {
            font-size: 2.5rem;
            margin-bottom: 16px;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        p {
            font-size: 1.1rem;
            line-height: 1.6;
            color: #a8a8b8;
            margin-bottom: 32px;
        }
        .status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 12px 24px;
            background: rgba(255,255,255,0.05);
            border-radius: 50px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .dot {
            width: 8px;
            height: 8px;
            background: #00ff88;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        code {
            background: rgba(255,255,255,0.1);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <svg class="logo" viewBox="0 -960 960 960" fill="#00d4ff">
            <path d="M200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h560q33 0 56.5 23.5T840-760v560q0 33-23.5 56.5T760-120H200Zm0-80h560v-480H200v480Zm280-80q-83 0-141.5-58.5T280-480q0-83 58.5-141.5T480-680q83 0 141.5 58.5T680-480q0 83-58.5 141.5T480-280Zm0-80q50 0 85-35t35-85q0-50-35-85t-85-35q-50 0-85 35t-35 85q0 50 35 85t85 35Z"/>
        </svg>
        <h1>Canvas Workspace</h1>
        <p>
            Your visual workspace is ready. Write an <code>index.html</code> file
            to this directory and it will appear here automatically.
        </p>
        <div class="status">
            <span class="dot"></span>
            <span>Watching for changes...</span>
        </div>
    </div>
    <script>
        // Auto-reload when index.html is created
        setInterval(() => {
            fetch(window.location.href, { method: 'HEAD' })
                .then(r => {
                    if (r.headers.get('content-length') !== document.body.innerHTML.length.toString()) {
                        window.location.reload();
                    }
                })
                .catch(() => {});
        }, 1000);
    </script>
</body>
</html>
"""


class CanvasManager:
    """
    Manages a visual workspace for agents.

    Provides:
    - HTTP server for serving workspace files
    - Browser control via Playwright
    - DOM querying and JavaScript evaluation
    - Screenshot capture
    - File watching with auto-reload
    """

    def __init__(self, config: Optional[CanvasConfig] = None):
        self.config = config or CanvasConfig()
        self.state = CanvasState()
        self._lock = asyncio.Lock()

    @staticmethod
    def find_free_port() -> int:
        """Find an available port on localhost."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    async def start(self, workspace_dir: Optional[str] = None) -> str:
        """
        Start the Canvas workspace.

        Args:
            workspace_dir: Directory to serve. Creates temp dir if not specified.

        Returns:
            The URL where the workspace is served.
        """
        async with self._lock:
            if self.state.is_running:
                return self.state.server_url

            # Setup workspace directory
            if workspace_dir:
                self.state.workspace_dir = os.path.abspath(workspace_dir)
            else:
                self.state.workspace_dir = files.get_abs_path("tmp/canvas/workspace")

            os.makedirs(self.state.workspace_dir, exist_ok=True)

            # Start HTTP server
            self.state.server_port = self.find_free_port()
            self.state.server_url = f"http://127.0.0.1:{self.state.server_port}"

            handler = partial(
                SilentHTTPRequestHandler,
                directory=self.state.workspace_dir
            )
            self.state.http_server = HTTPServer(
                ('127.0.0.1', self.state.server_port),
                handler
            )

            self.state.server_thread = threading.Thread(
                target=self.state.http_server.serve_forever,
                daemon=True,
                name=f"CanvasServer-{self.state.server_port}"
            )
            self.state.server_thread.start()

            # Start browser if Playwright is available
            if PLAYWRIGHT_AVAILABLE:
                try:
                    await self._start_browser()
                except Exception as e:
                    PrintStyle().warning(f"Canvas: Browser initialization failed: {e}")

            # Start file watcher if auto_reload is enabled
            if self.config.auto_reload:
                self.state.watcher_task = asyncio.create_task(self._watch_files())

            self.state.is_running = True
            PrintStyle().print(f"Canvas started at {self.state.server_url} (workspace: {self.state.workspace_dir})")

            return self.state.server_url

    async def _start_browser(self):
        """Initialize Playwright browser."""
        if not PLAYWRIGHT_AVAILABLE:
            return

        try:
            pw_binary = ensure_playwright_binary()
        except Exception:
            pw_binary = None

        self.state.playwright = await async_playwright().start()

        launch_args = {
            'headless': self.config.headless,
            'args': [
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                f'--window-size={self.config.window_width},{self.config.window_height}',
            ]
        }

        if pw_binary:
            launch_args['executable_path'] = str(pw_binary)

        self.state.browser = await self.state.playwright.chromium.launch(**launch_args)
        self.state.page = await self.state.browser.new_page()
        await self.state.page.set_viewport_size({
            'width': self.config.window_width,
            'height': self.config.window_height
        })

        # Navigate to workspace
        await self.state.page.goto(self.state.server_url)

    async def _watch_files(self):
        """Watch workspace directory for changes and auto-reload."""
        last_mtime = 0

        while self.state.is_running:
            try:
                await asyncio.sleep(0.5)  # Check every 500ms

                # Get latest mtime in workspace
                current_mtime = 0
                for root, _, filenames in os.walk(self.state.workspace_dir):
                    for f in filenames:
                        try:
                            mtime = os.path.getmtime(os.path.join(root, f))
                            current_mtime = max(current_mtime, mtime)
                        except OSError:
                            pass

                # Reload if files changed (with debounce)
                if current_mtime > last_mtime:
                    now = time.time()
                    if now - self.state.last_reload_time > self.config.reload_debounce_ms / 1000:
                        last_mtime = current_mtime
                        self.state.last_reload_time = now
                        await self.reload()

            except asyncio.CancelledError:
                break
            except Exception as e:
                PrintStyle().warning(f"Canvas watcher error: {e}")

    async def stop(self):
        """Stop the Canvas workspace."""
        async with self._lock:
            self.state.is_running = False

            # Cancel file watcher
            if self.state.watcher_task:
                self.state.watcher_task.cancel()
                try:
                    await self.state.watcher_task
                except asyncio.CancelledError:
                    pass
                self.state.watcher_task = None

            # Close browser
            if self.state.page:
                try:
                    await self.state.page.close()
                except Exception:
                    pass
                self.state.page = None

            if self.state.browser:
                try:
                    await self.state.browser.close()
                except Exception:
                    pass
                self.state.browser = None

            if self.state.playwright:
                try:
                    await self.state.playwright.stop()
                except Exception:
                    pass
                self.state.playwright = None

            # Stop HTTP server
            if self.state.http_server:
                self.state.http_server.shutdown()
                self.state.http_server = None

            if self.state.server_thread:
                self.state.server_thread.join(timeout=2)
                self.state.server_thread = None

            PrintStyle().print("Canvas stopped")

    async def navigate(self, path: str) -> tuple[str, str]:
        """
        Navigate to a path within the workspace.

        Args:
            path: Relative path (e.g., '/app' or '/dashboard')

        Returns:
            Tuple of (final_url, page_title)
        """
        if not self.state.page:
            raise RuntimeError("Canvas browser not initialized")

        # Normalize path
        if not path.startswith('/'):
            path = '/' + path

        url = f"{self.state.server_url}{path}"
        await self.state.page.goto(url, wait_until='domcontentloaded')

        title = await self.state.page.title()
        location = self.state.page.url

        return location, title

    async def reload(self):
        """Reload the current page."""
        if self.state.page:
            try:
                await self.state.page.reload(wait_until='domcontentloaded')
            except Exception:
                pass

    async def eval(self, js_code: str) -> Any:
        """
        Evaluate JavaScript in the page context.

        Args:
            js_code: JavaScript code to execute.

        Returns:
            The result of the JavaScript evaluation.
        """
        if not self.state.page:
            raise RuntimeError("Canvas browser not initialized")

        return await self.state.page.evaluate(js_code)

    async def query(self, selector: str, mode: str = 'text') -> str:
        """
        Query DOM elements.

        Args:
            selector: CSS selector
            mode: 'text' for textContent, 'outer_html' for outerHTML

        Returns:
            The queried content.
        """
        if not self.state.page:
            raise RuntimeError("Canvas browser not initialized")

        if mode == 'outer_html':
            return await self.state.page.evaluate(
                f'document.querySelector({repr(selector)})?.outerHTML || ""'
            )
        else:  # text
            return await self.state.page.evaluate(
                f'document.querySelector({repr(selector)})?.textContent || ""'
            )

    async def query_all(self, selector: str, mode: str = 'text') -> list[str]:
        """
        Query all matching DOM elements.

        Args:
            selector: CSS selector
            mode: 'text' for textContent, 'outer_html' for outerHTML

        Returns:
            List of queried content for each match.
        """
        if not self.state.page:
            raise RuntimeError("Canvas browser not initialized")

        if mode == 'outer_html':
            return await self.state.page.evaluate(
                f'Array.from(document.querySelectorAll({repr(selector)})).map(el => el.outerHTML)'
            )
        else:  # text
            return await self.state.page.evaluate(
                f'Array.from(document.querySelectorAll({repr(selector)})).map(el => el.textContent || "")'
            )

    async def screenshot(self, selector: Optional[str] = None, path: Optional[str] = None) -> str:
        """
        Capture a screenshot.

        Args:
            selector: Optional CSS selector to screenshot specific element.
            path: Optional path to save screenshot. Auto-generated if not provided.

        Returns:
            Path to the saved screenshot.
        """
        if not self.state.page:
            raise RuntimeError("Canvas browser not initialized")

        if not path:
            screenshots_dir = files.get_abs_path("tmp/canvas/screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            path = os.path.join(screenshots_dir, f"canvas_{int(time.time() * 1000)}.png")

        if selector:
            element = await self.state.page.query_selector(selector)
            if element:
                await element.screenshot(path=path)
            else:
                raise ValueError(f"Element not found: {selector}")
        else:
            await self.state.page.screenshot(path=path)

        return path

    async def click(self, selector: str):
        """Click an element."""
        if not self.state.page:
            raise RuntimeError("Canvas browser not initialized")

        await self.state.page.click(selector)

    async def type_text(self, selector: str, text: str, clear: bool = False):
        """Type text into an element."""
        if not self.state.page:
            raise RuntimeError("Canvas browser not initialized")

        if clear:
            await self.state.page.fill(selector, '')
        await self.state.page.type(selector, text)

    async def wait_for(self, selector: str, state: str = 'visible', timeout: int = 10000):
        """
        Wait for an element state.

        Args:
            selector: CSS selector
            state: 'visible', 'hidden', 'attached', 'detached'
            timeout: Timeout in milliseconds
        """
        if not self.state.page:
            raise RuntimeError("Canvas browser not initialized")

        await self.state.page.wait_for_selector(selector, state=state, timeout=timeout)

    def write_file(self, relative_path: str, content: str):
        """
        Write a file to the workspace.

        Args:
            relative_path: Path relative to workspace root
            content: File content
        """
        full_path = os.path.join(self.state.workspace_dir, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def read_file(self, relative_path: str) -> str:
        """
        Read a file from the workspace.

        Args:
            relative_path: Path relative to workspace root

        Returns:
            File content
        """
        full_path = os.path.join(self.state.workspace_dir, relative_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()

    def list_files(self, relative_path: str = '') -> list[str]:
        """
        List files in the workspace.

        Args:
            relative_path: Optional subdirectory path

        Returns:
            List of file paths relative to workspace root
        """
        base = os.path.join(self.state.workspace_dir, relative_path)
        result = []

        for root, _, filenames in os.walk(base):
            for f in filenames:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self.state.workspace_dir)
                result.append(rel_path)

        return sorted(result)

    def get_status(self) -> dict:
        """Get current Canvas status."""
        return {
            'running': self.state.is_running,
            'url': self.state.server_url,
            'port': self.state.server_port,
            'workspace': self.state.workspace_dir,
            'browser_ready': self.state.page is not None,
            'auto_reload': self.config.auto_reload,
        }


# Singleton instance for shared canvas
_canvas_instances: dict[str, CanvasManager] = {}


def get_canvas(context_id: str, config: Optional[CanvasConfig] = None) -> CanvasManager:
    """Get or create a Canvas instance for a context."""
    if context_id not in _canvas_instances:
        _canvas_instances[context_id] = CanvasManager(config)
    return _canvas_instances[context_id]


async def cleanup_canvas(context_id: str):
    """Clean up a Canvas instance."""
    if context_id in _canvas_instances:
        await _canvas_instances[context_id].stop()
        del _canvas_instances[context_id]
