"""
Canvas Tool - Visual Workspace for Agent Zero

Allows agents to create, view, and interact with HTML/CSS/JS content
in a real browser environment.
"""

import os
import time
from python.helpers.tool import Tool, Response
from python.helpers import files
from python.helpers.canvas import CanvasManager, CanvasConfig, get_canvas, cleanup_canvas
from python.helpers.print_style import PrintStyle


class Canvas(Tool):
    """
    Visual workspace tool for creating and previewing web content.

    Actions:
        start      - Start canvas workspace (optional: path to workspace directory)
        stop       - Stop canvas workspace
        navigate   - Navigate to a path within workspace
        write      - Write a file to workspace
        read       - Read a file from workspace
        list       - List files in workspace
        eval       - Evaluate JavaScript in the page
        query      - Query DOM elements (selector, mode: text|outer_html)
        query_all  - Query all matching DOM elements
        screenshot - Capture screenshot (optional: selector)
        click      - Click an element
        type       - Type text into an element
        wait       - Wait for element state
        reload     - Reload the page
        status     - Get canvas status
    """

    async def execute(
        self,
        action: str = "status",
        path: str = "",
        content: str = "",
        selector: str = "",
        mode: str = "text",
        text: str = "",
        clear: str = "false",
        state: str = "visible",
        timeout: str = "10000",
        **kwargs
    ) -> Response:
        """Execute canvas action."""

        action = action.lower().strip()
        canvas = get_canvas(self.agent.context.id, self._get_config())

        try:
            match action:
                case "start":
                    workspace = path if path else None
                    url = await canvas.start(workspace)
                    status = canvas.get_status()
                    return Response(
                        message=f"Canvas started.\nURL: {url}\nWorkspace: {status['workspace']}\nBrowser ready: {status['browser_ready']}",
                        break_loop=False
                    )

                case "stop":
                    await canvas.stop()
                    return Response(message="Canvas stopped.", break_loop=False)

                case "navigate":
                    if not path:
                        return Response(message="Error: 'path' is required for navigate action.", break_loop=False)
                    location, title = await canvas.navigate(path)
                    return Response(
                        message=f"Navigated to: {location}\nTitle: {title}",
                        break_loop=False
                    )

                case "write":
                    if not path:
                        return Response(message="Error: 'path' is required for write action.", break_loop=False)
                    if not content:
                        return Response(message="Error: 'content' is required for write action.", break_loop=False)
                    canvas.write_file(path, content)
                    return Response(
                        message=f"File written: {path} ({len(content)} bytes)",
                        break_loop=False
                    )

                case "read":
                    if not path:
                        return Response(message="Error: 'path' is required for read action.", break_loop=False)
                    file_content = canvas.read_file(path)
                    return Response(
                        message=f"Content of {path}:\n{file_content}",
                        break_loop=False
                    )

                case "list":
                    file_list = canvas.list_files(path)
                    if file_list:
                        return Response(
                            message=f"Files in workspace:\n" + "\n".join(f"  - {f}" for f in file_list),
                            break_loop=False
                        )
                    else:
                        return Response(message="Workspace is empty.", break_loop=False)

                case "eval":
                    if not content:
                        return Response(message="Error: 'content' (JavaScript code) is required for eval action.", break_loop=False)
                    # Preprocess §§include() directives - replace with file contents
                    processed_content = self._preprocess_includes(content, canvas)
                    result = await canvas.eval(processed_content)
                    return Response(
                        message=f"JavaScript result:\n{result}",
                        break_loop=False
                    )

                case "query":
                    if not selector:
                        return Response(message="Error: 'selector' is required for query action.", break_loop=False)
                    result = await canvas.query(selector, mode)
                    return Response(
                        message=f"Query result ({mode}):\n{result}",
                        break_loop=False
                    )

                case "query_all":
                    if not selector:
                        return Response(message="Error: 'selector' is required for query_all action.", break_loop=False)
                    results = await canvas.query_all(selector, mode)
                    if results:
                        formatted = "\n".join(f"[{i}] {r}" for i, r in enumerate(results))
                        return Response(
                            message=f"Query all results ({len(results)} matches):\n{formatted}",
                            break_loop=False
                        )
                    else:
                        return Response(message="No elements found.", break_loop=False)

                case "screenshot":
                    sel = selector if selector else None
                    img_path = await canvas.screenshot(selector=sel)
                    return Response(
                        message=f"Screenshot saved: {img_path}",
                        break_loop=False,
                        additional={"screenshot": f"img://{img_path}"}
                    )

                case "click":
                    if not selector:
                        return Response(message="Error: 'selector' is required for click action.", break_loop=False)
                    await canvas.click(selector)
                    return Response(message=f"Clicked: {selector}", break_loop=False)

                case "type":
                    if not selector:
                        return Response(message="Error: 'selector' is required for type action.", break_loop=False)
                    if not text:
                        return Response(message="Error: 'text' is required for type action.", break_loop=False)
                    should_clear = clear.lower() == "true"
                    await canvas.type_text(selector, text, clear=should_clear)
                    return Response(
                        message=f"Typed into {selector}: {text[:50]}{'...' if len(text) > 50 else ''}",
                        break_loop=False
                    )

                case "wait":
                    if not selector:
                        return Response(message="Error: 'selector' is required for wait action.", break_loop=False)
                    timeout_ms = int(timeout)
                    await canvas.wait_for(selector, state=state, timeout=timeout_ms)
                    return Response(
                        message=f"Element {selector} is now {state}",
                        break_loop=False
                    )

                case "reload":
                    await canvas.reload()
                    return Response(message="Page reloaded.", break_loop=False)

                case "status":
                    status = canvas.get_status()
                    lines = [
                        f"Running: {status['running']}",
                        f"URL: {status['url'] or 'N/A'}",
                        f"Port: {status['port'] or 'N/A'}",
                        f"Workspace: {status['workspace'] or 'N/A'}",
                        f"Browser ready: {status['browser_ready']}",
                        f"Auto-reload: {status['auto_reload']}",
                    ]
                    return Response(
                        message="Canvas Status:\n" + "\n".join(lines),
                        break_loop=False
                    )

                case _:
                    return Response(
                        message=f"Unknown action: {action}. Valid actions: start, stop, navigate, write, read, list, eval, query, query_all, screenshot, click, type, wait, reload, status",
                        break_loop=False
                    )

        except RuntimeError as e:
            if "not initialized" in str(e):
                return Response(
                    message=f"Canvas not started. Use action='start' first.\nError: {e}",
                    break_loop=False
                )
            raise
        except Exception as e:
            return Response(
                message=f"Canvas error: {type(e).__name__}: {e}",
                break_loop=False
            )

    def _get_config(self) -> CanvasConfig:
        """Get canvas configuration from agent settings."""
        settings = self.agent.config
        return CanvasConfig(
            headless=getattr(settings, 'canvas_headless', True),
            auto_reload=getattr(settings, 'canvas_auto_reload', True),
        )

    def _preprocess_includes(self, content: str, canvas: 'CanvasManager') -> str:
        """
        Preprocess §§include() directives in JavaScript content.

        Replaces §§include(/path/to/file) with the JSON-escaped file contents.
        This allows agents to inject file data into JavaScript code.
        """
        import re
        import json

        pattern = r'§§include\(([^)]+)\)'

        def replace_include(match):
            file_path = match.group(1).strip()
            try:
                # Try reading from workspace first (relative path)
                if not os.path.isabs(file_path):
                    try:
                        file_content = canvas.read_file(file_path)
                    except Exception:
                        # Fall back to absolute path
                        file_content = files.read_file(file_path)
                else:
                    file_content = files.read_file(file_path)

                # Try to parse as JSON first for proper escaping
                try:
                    parsed = json.loads(file_content)
                    return json.dumps(parsed)  # Re-serialize for JS-safe output
                except json.JSONDecodeError:
                    # Not JSON, escape as string
                    return json.dumps(file_content)
            except Exception as e:
                # Return error message in JS-safe format
                return json.dumps(f"[Include Error: {e}]")

        return re.sub(pattern, replace_include, content)

    def get_log_object(self):
        action = self.args.get('action', 'status') if self.args else 'status'
        return self.agent.context.log.log(
            type="canvas",
            heading=f"icon://web {self.agent.agent_name}: Canvas [{action}]",
            content="",
            kvps=self.args,
        )
