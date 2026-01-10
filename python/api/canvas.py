"""
Canvas API - Frontend interface for Canvas visual workspace
"""

from python.helpers.api import ApiHandler, Request, Response
from python.helpers.canvas import get_canvas, cleanup_canvas, CanvasConfig
from python.helpers.print_style import PrintStyle


class Canvas(ApiHandler):
    """API endpoint for Canvas visual workspace operations."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = input.get("action", "status")
        ctxid = input.get("ctxid", "")

        # Get or create canvas for this context
        config = CanvasConfig(
            headless=input.get("headless", True),
            auto_reload=input.get("auto_reload", True),
        )

        try:
            match action:
                case "start":
                    workspace = input.get("workspace", None)
                    canvas = get_canvas(ctxid, config)
                    url = await canvas.start(workspace)
                    status = canvas.get_status()
                    PrintStyle(background_color="#7B2CBF", font_color="white", padding=True).print(
                        f"Canvas started: {url}"
                    )
                    return {
                        "status": "ok",
                        "action": "start",
                        "url": status["url"],
                        "port": status["port"],
                        "workspace": status["workspace"],
                        "browser_ready": status["browser_ready"],
                    }

                case "stop":
                    await cleanup_canvas(ctxid)
                    PrintStyle(background_color="#7B2CBF", font_color="white", padding=True).print(
                        "Canvas stopped"
                    )
                    return {"status": "ok", "action": "stop"}

                case "status":
                    canvas = get_canvas(ctxid, config)
                    status = canvas.get_status()
                    return {
                        "status": "ok",
                        "action": "status",
                        **status,
                    }

                case "screenshot":
                    canvas = get_canvas(ctxid, config)
                    if not canvas.state.is_running:
                        return Response("Canvas not running", status=400)
                    selector = input.get("selector", None)
                    path = await canvas.screenshot(selector=selector)
                    return {
                        "status": "ok",
                        "action": "screenshot",
                        "path": path,
                    }

                case "navigate":
                    canvas = get_canvas(ctxid, config)
                    if not canvas.state.is_running:
                        return Response("Canvas not running", status=400)
                    path = input.get("path", "/")
                    location, title = await canvas.navigate(path)
                    return {
                        "status": "ok",
                        "action": "navigate",
                        "location": location,
                        "title": title,
                    }

                case "reload":
                    canvas = get_canvas(ctxid, config)
                    if not canvas.state.is_running:
                        return Response("Canvas not running", status=400)
                    await canvas.reload()
                    return {"status": "ok", "action": "reload"}

                case "files":
                    canvas = get_canvas(ctxid, config)
                    if not canvas.state.is_running:
                        return {"status": "ok", "action": "files", "files": []}
                    files = canvas.list_files()
                    return {
                        "status": "ok",
                        "action": "files",
                        "files": files,
                    }

                case "write":
                    canvas = get_canvas(ctxid, config)
                    if not canvas.state.is_running:
                        return Response("Canvas not running", status=400)
                    path = input.get("path", "")
                    content = input.get("content", "")
                    if not path:
                        return Response("path is required", status=400)
                    canvas.write_file(path, content)
                    return {
                        "status": "ok",
                        "action": "write",
                        "path": path,
                        "size": len(content),
                    }

                case _:
                    return Response(f"Unknown action: {action}", status=400)

        except Exception as e:
            PrintStyle(background_color="red", font_color="white", padding=True).print(
                f"Canvas error: {e}"
            )
            return Response(f"Canvas error: {str(e)}", status=500)
