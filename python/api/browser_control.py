from python.helpers.api import ApiHandler, Request, Response


class BrowserControl(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        # input data
        ctxid = input.get("context", "")
        
        # context instance - get or create
        context = self.get_context(ctxid)
        
        # Get the agent from context and check for active browser agent
        agent = context.agent0
        if not agent:
            return {
                "error": "No agent found in context",
                "active": False,
                "ws_endpoint": None,
                "devtools_link": None
            }
        
        browser_state = agent.get_data("_browser_agent_state")
        
        if not browser_state:
            return {
                "error": "No active browser session found",
                "active": False,
                "ws_endpoint": None,
                "devtools_link": None
            }
        
        # Return browser control information
        result = {
            "active": True,
            "environment": "docker" if browser_state.is_docker else "local",
            "control_options": [],
            "ws_endpoint": browser_state.ws_endpoint,
            "devtools_link": None,
            "vnc_url": browser_state.vnc_url,
            "display_port": browser_state.display_port
        }
        
        # Add CDP control if available
        if browser_state.ws_endpoint:
            ws_path = browser_state.ws_endpoint.replace("ws://", "").replace("wss://", "")
            devtools_link = f"chrome-devtools://devtools/bundled/inspector.html?ws={ws_path}"
            result["devtools_link"] = devtools_link
            result["control_options"].append({
                "type": "cdp",
                "devtools_link": devtools_link,
                "ws_endpoint": browser_state.ws_endpoint
            })
        
        # Add VNC control if available
        if browser_state.vnc_url and browser_state.display_port:
            result["control_options"].append({
                "type": "vnc",
                "vnc_url": browser_state.vnc_url,
                "display_port": browser_state.display_port
            })
        
        return result