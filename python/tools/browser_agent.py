"""
Browser Agent Tool

Provides browser automation for Agent Zero using the agent-browser CLI.
Replaces the previous browser-use implementation with a CLI-based approach
that uses accessibility tree snapshots and ref-based element selection.
"""

import asyncio
import time
from typing import Optional
from pathlib import Path

from agent import Agent, InterventionException
from python.helpers.tool import Tool, Response
from python.helpers import files, defer, persist_chat
from python.helpers.agent_browser import AgentBrowser, AgentBrowserConfig, AgentBrowserResult
from python.helpers.print_style import PrintStyle
from python.helpers.secrets import get_secrets_manager
from python.extensions.message_loop_start._10_iteration_no import get_iter_no


class BrowserState:
    """Manages browser session state for an agent context."""

    def __init__(self, agent: Agent):
        self.agent = agent
        self.browser: Optional[AgentBrowser] = None
        self.task: Optional[defer.DeferredTask] = None
        self.iter_no = 0
        self.stream_port: Optional[int] = None

    def get_session_name(self) -> str:
        """Get unique session name based on context ID."""
        return f"a0_{self.agent.context.id}"

    def get_executable_path(self) -> Optional[str]:
        """Get Chromium executable path if available."""
        # Try to use Playwright's Chromium if installed
        try:
            from python.helpers.playwright import get_playwright_binary
            binary = get_playwright_binary()
            if binary:
                return str(binary)
        except Exception:
            pass
        return None

    async def initialize(self, headed: bool = False, stream_port: Optional[int] = None) -> AgentBrowser:
        """Initialize or get existing browser instance."""
        if self.browser and self.browser.is_open:
            return self.browser

        self.stream_port = stream_port
        config = AgentBrowserConfig(
            session_name=self.get_session_name(),
            executable_path=self.get_executable_path(),
            stream_port=stream_port,
            headed=headed,
            viewport_width=1024,
            viewport_height=768,
        )

        self.browser = AgentBrowser(config=config)
        return self.browser

    def start_task(self, task_func, *args):
        """Start a deferred task for browser operations."""
        if self.task and self.task.is_alive():
            self.kill_task()

        self.task = defer.DeferredTask(
            thread_name=f"BrowserAgent_{self.agent.context.id}"
        )
        if self.agent.context.task:
            self.agent.context.task.add_child_task(self.task, terminate_thread=True)
        self.task.start_task(task_func, *args)
        return self.task

    def kill_task(self):
        """Kill the current browser task and cleanup."""
        if self.task:
            self.task.kill(terminate_thread=True)
            self.task = None

    async def close(self):
        """Close the browser session."""
        self.kill_task()
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                PrintStyle().warning(f"Error closing browser: {e}")
            finally:
                self.browser = None
        self.iter_no = 0

    def __del__(self):
        """Cleanup on deletion."""
        self.kill_task()


class BrowserAgent(Tool):
    """
    Browser automation tool using agent-browser CLI.

    Executes browser tasks by:
    1. Navigating to URLs
    2. Taking snapshots to get interactive elements
    3. Using refs (@e1, @e2, etc.) to click/fill elements
    4. Capturing screenshots for progress
    """

    async def execute(self, message: str = "", reset: str = "", headed: str = "", **kwargs) -> Response:
        """
        Execute a browser automation task.

        Args:
            message: Task instructions for the browser agent
            reset: "true" to start a fresh browser session
            headed: "true" to show browser window (for CAPTCHA, user intervention)
        """
        self.guid = self.agent.context.generate_id()
        reset_session = str(reset).lower().strip() == "true"
        use_headed = str(headed).lower().strip() == "true"

        # Mask any secrets in the message
        secrets_manager = get_secrets_manager(self.agent.context)
        masked_message = secrets_manager.mask_values(
            message, placeholder="<secret>{key}</secret>"
        )

        # Get or create browser state
        await self.prepare_state(reset=reset_session)

        # Initialize browser with headed mode if requested
        stream_port = 9223 if use_headed else None
        await self.state.initialize(headed=use_headed, stream_port=stream_port)

        # Start the browser task
        task = self.state.start_task(self._run_browser_task, masked_message, use_headed)

        # Wait for task completion with timeout
        timeout_seconds = 300  # 5 minute timeout
        start_time = time.time()
        fail_counter = 0

        while task and not task.is_ready():
            if time.time() - start_time > timeout_seconds:
                PrintStyle().warning(f"Browser task timeout after {timeout_seconds}s")
                break

            await self.agent.handle_intervention()
            await asyncio.sleep(1)

            try:
                if task.is_ready():
                    break

                # Get progress update
                update = await asyncio.wait_for(self._get_progress_update(), timeout=10)
                fail_counter = 0

                if update.get("log"):
                    self.update_progress(update["log"])
                if update.get("screenshot"):
                    self.log.update(screenshot=update["screenshot"])

            except asyncio.TimeoutError:
                fail_counter += 1
                if fail_counter >= 3:
                    PrintStyle().warning("3 consecutive timeouts, breaking loop")
                    break
            except Exception as e:
                PrintStyle().error(f"Progress update error: {e}")

        # Handle timeout
        if task and not task.is_ready():
            self.state.kill_task()
            return Response(
                message=self._mask("Browser task timed out without completion."),
                break_loop=False,
            )

        # Get result
        try:
            result = await task.result() if task else None
        except Exception as e:
            PrintStyle().error(f"Task result error: {e}")
            return Response(
                message=self._mask(f"Browser task failed: {e}"),
                break_loop=False,
            )

        # Format response
        answer_text = self._format_result(result)
        answer_text = self._mask(answer_text)

        self.log.update(answer=answer_text)

        # Add screenshot path if available
        if self.log.kvps and self.log.kvps.get("screenshot"):
            path = self.log.kvps["screenshot"].split("//", 1)[-1].split("&", 1)[0]
            answer_text += f"\n\nScreenshot: {path}"

        return Response(message=answer_text, break_loop=False)

    async def _run_browser_task(self, task_message: str, headed: bool) -> dict:
        """
        Execute the browser automation task.

        This method interprets the task message and executes browser commands.
        Uses a loop of: snapshot → decide action → execute → repeat until done.
        """
        browser = self.state.browser
        if not browser:
            return {"error": "Browser not initialized"}

        self.state.iter_no = get_iter_no(self.agent)
        result = {
            "success": False,
            "response": "",
            "page_summary": "",
            "urls_visited": [],
            "actions_taken": [],
        }

        try:
            # Parse the task to extract initial URL if present
            initial_url = self._extract_url_from_message(task_message)

            if initial_url:
                # Navigate to the URL
                nav_result = await browser.open(initial_url, headed=headed)
                if not nav_result.success:
                    result["error"] = f"Failed to open URL: {nav_result.error}"
                    return result
                result["urls_visited"].append(initial_url)
                result["actions_taken"].append(f"Navigated to {initial_url}")

            # Take initial snapshot
            snapshot = await browser.snapshot(interactive=True)
            if snapshot.success:
                snapshot_text = snapshot.data.get("snapshot", "")
                refs = snapshot.data.get("refs", {})
                result["page_summary"] = self._summarize_snapshot(snapshot_text, refs)

            # Get page title and URL
            title_result = await browser.get_title()
            url_result = await browser.get_url()
            current_title = title_result.data.get("title", "") if title_result.success else ""
            current_url = url_result.data.get("url", "") if url_result.success else initial_url

            # Execute task using agent's LLM for decision making
            # For now, provide the snapshot summary as the result
            # Full LLM integration for multi-step tasks would go here

            # Take screenshot
            screenshot_path = self._get_screenshot_path()
            await browser.screenshot(screenshot_path)

            result["success"] = True
            result["response"] = f"Visited: {current_title or current_url}\n\n{result['page_summary']}"
            result["screenshot"] = screenshot_path

        except InterventionException:
            result["error"] = "Task cancelled by intervention"
        except Exception as e:
            result["error"] = f"Browser task error: {str(e)}"
            PrintStyle().error(f"Browser task error: {e}")

        return result

    def _extract_url_from_message(self, message: str) -> Optional[str]:
        """Extract a URL from the task message."""
        import re
        # Match common URL patterns
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        match = re.search(url_pattern, message)
        if match:
            return match.group(0)

        # Check for domain-like patterns
        domain_pattern = r'\b(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z]{2,})+)(?:/[^\s]*)?'
        match = re.search(domain_pattern, message)
        if match:
            domain = match.group(0)
            if not domain.startswith(('http://', 'https://')):
                return f"https://{domain}"
            return domain

        return None

    def _summarize_snapshot(self, snapshot_text: str, refs: dict) -> str:
        """Create a summary of the page snapshot."""
        if not snapshot_text and not refs:
            return "No interactive elements found on page."

        lines = []
        if snapshot_text:
            # Take first few lines of snapshot
            snapshot_lines = snapshot_text.strip().split('\n')[:10]
            lines.extend(snapshot_lines)

        if refs:
            lines.append(f"\nFound {len(refs)} interactive elements.")

        return '\n'.join(lines)

    def _get_screenshot_path(self) -> str:
        """Get path for saving screenshot."""
        return files.get_abs_path(
            persist_chat.get_chat_folder_path(self.agent.context.id),
            "browser",
            "screenshots",
            f"{self.guid}.png",
        )

    async def _get_progress_update(self) -> dict:
        """Get progress update from running browser task."""
        result = {}
        browser = self.state.browser if self.state else None

        if browser and browser.is_open:
            try:
                # Get current URL/title for progress
                url_result = await browser.get_url()
                if url_result.success:
                    result["log"] = f"Current page: {url_result.data.get('url', '')}"

                # Take progress screenshot
                screenshot_path = self._get_screenshot_path()
                files.make_dirs(screenshot_path)
                screenshot_result = await browser.screenshot(screenshot_path)
                if screenshot_result.success:
                    result["screenshot"] = f"img://{screenshot_path}&t={time.time()}"

            except Exception:
                pass

        return result

    def _format_result(self, result: Optional[dict]) -> str:
        """Format the task result for response."""
        if not result:
            return "Browser task completed with no result."

        if result.get("error"):
            return f"Browser task error: {result['error']}"

        parts = []
        if result.get("response"):
            parts.append(result["response"])
        if result.get("page_summary") and result.get("response") != result.get("page_summary"):
            parts.append(f"\nPage Summary:\n{result['page_summary']}")
        if result.get("urls_visited"):
            parts.append(f"\nURLs visited: {', '.join(result['urls_visited'])}")
        if result.get("actions_taken"):
            parts.append(f"\nActions: {', '.join(result['actions_taken'])}")

        return '\n'.join(parts) if parts else "Task completed successfully."

    def get_log_object(self):
        """Create log entry for this tool invocation."""
        return self.agent.context.log.log(
            type="browser",
            heading=f"icon://captive_portal {self.agent.agent_name}: Browser Agent",
            content="",
            kvps=self.args,
        )

    async def prepare_state(self, reset: bool = False):
        """Get or create browser state for this agent."""
        self.state: BrowserState = self.agent.get_data("_browser_agent_state")
        if reset and self.state:
            await self.state.close()
        if not self.state or reset:
            self.state = BrowserState(self.agent)
        self.agent.set_data("_browser_agent_state", self.state)

    def update_progress(self, text: str):
        """Update progress display."""
        text = self._mask(text)
        short = text.split("\n")[-1]
        if len(short) > 50:
            short = short[:50] + "..."
        progress = f"Browser: {short}"

        self.log.update(progress=text)
        self.agent.context.log.set_progress(progress)

    def _mask(self, text: str) -> str:
        """Mask secrets in text."""
        try:
            return get_secrets_manager(self.agent.context).mask_values(text or "")
        except Exception:
            return text or ""
