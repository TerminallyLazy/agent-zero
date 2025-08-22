import asyncio
import time
import os
import subprocess
from typing import Optional, cast
from agent import Agent, InterventionException
from pathlib import Path

from python.helpers.tool import Tool, Response
from python.helpers import files, defer, persist_chat, strings
from python.helpers.browser_use import browser_use  # type: ignore[attr-defined]
from python.helpers.print_style import PrintStyle
from python.helpers.playwright import ensure_playwright_binary
from python.helpers.secrets import SecretsManager
from python.extensions.message_loop_start._10_iteration_no import get_iter_no
from pydantic import BaseModel
import uuid
from python.helpers.dirty_json import DirtyJson


class State:
    @staticmethod
    async def create(agent: Agent):
        state = State(agent)
        return state

    def __init__(self, agent: Agent):
        self.agent = agent
        self.browser_session: Optional[browser_use.BrowserSession] = None
        self.task: Optional[defer.DeferredTask] = None
        self.use_agent: Optional[browser_use.Agent] = None
        self.secrets_dict: Optional[dict[str, str]] = None
        self.iter_no = 0
        self.ws_endpoint: Optional[str] = None
        self.vnc_url: Optional[str] = None
        self.display_port: Optional[int] = None
        self.is_docker = self._detect_docker_environment()

    def __del__(self):
        self.kill_task()

    def _detect_docker_environment(self) -> bool:
        """Detect if running inside Docker container"""
        try:
            # Check for common Docker indicators
            if os.path.exists('/.dockerenv'):
                return True
            if os.path.exists('/proc/1/cgroup'):
                with open('/proc/1/cgroup', 'r') as f:
                    content = f.read()
                    if 'docker' in content or 'containerd' in content:
                        return True
            return False
        except Exception:
            return False

    def _setup_virtual_display(self) -> Optional[int]:
        """Setup virtual display for headless Docker environment"""
        if not self.is_docker:
            return None
            
        try:
            # Find available display port
            for display_num in range(1, 100):
                display_port = 5900 + display_num
                # Check if port is available
                result = subprocess.run(['netstat', '-ln'], 
                                      capture_output=True, text=True)
                if f':{display_port} ' not in result.stdout:
                    # Start Xvfb on this display
                    subprocess.Popen([
                        'Xvfb', f':{display_num}', 
                        '-screen', '0', '1920x1080x24',
                        '-ac', '+extension', 'GLX'
                    ])
                    
                    # Start x11vnc for remote access
                    subprocess.Popen([
                        'x11vnc', '-display', f':{display_num}',
                        '-rfbport', str(display_port),
                        '-forever', '-shared', '-nopw'
                    ])
                    
                    # Set DISPLAY environment variable
                    os.environ['DISPLAY'] = f':{display_num}'
                    
                    PrintStyle().print(f"Virtual display started on :{display_num}, VNC port {display_port}")
                    return display_port
            
            PrintStyle().warning("Could not find available display port")
            return None
            
        except Exception as e:
            PrintStyle().warning(f"Failed to setup virtual display: {e}")
            return None

    async def _initialize(self):
        if self.browser_session:
            return

        # Setup virtual display for Docker environment
        if self.is_docker:
            self.display_port = self._setup_virtual_display()
            if self.display_port:
                self.vnc_url = f"vnc://localhost:{self.display_port}"

        # for some reason we need to provide exact path to headless shell, otherwise it looks for headed browser
        pw_binary = ensure_playwright_binary()

        # Configure browser args based on environment
        browser_args = ["--remote-debugging-port=0"]  # Always enable CDP
        
        if self.is_docker:
            # Docker-specific args
            browser_args.extend([
                "--no-sandbox",
                "--disable-dev-shm-usage", 
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding"
            ])
            # Run headful if we have virtual display, headless otherwise
            headless_mode = self.display_port is None
            if not headless_mode:
                browser_args.append("--start-maximized")
        else:
            # Local development - can run headful or headless
            headless_mode = True
            browser_args.append("--headless=new")

        self.browser_session = browser_use.BrowserSession(
            browser_profile=browser_use.BrowserProfile(
                headless=headless_mode,
                disable_security=True,
                chromium_sandbox=False,
                accept_downloads=True,
                downloads_dir=files.get_abs_path("tmp/downloads"),
                downloads_path=files.get_abs_path("tmp/downloads"),
                executable_path=pw_binary,
                keep_alive=True,
                minimum_wait_page_load_time=1.0,
                wait_for_network_idle_page_load_time=2.0,
                maximum_wait_page_load_time=10.0,
                screen={"width": 1920, "height": 1080},
                viewport={"width": 1920, "height": 1080},
                args=browser_args,
                # Use a unique user data directory to avoid conflicts
                user_data_dir=str(
                    Path.home()
                    / ".config"
                    / "browseruse"
                    / "profiles"
                    / f"agent_{self.agent.context.id}"
                ),
            )
        )

        await self.browser_session.start() if self.browser_session else None
        
        # Capture CDP WebSocket endpoint after browser starts
        if self.browser_session and self.browser_session.browser_context:
            browser = self.browser_session.browser_context.browser
            # Get the WebSocket endpoint for DevTools connection
            try:
                # Try multiple approaches to get CDP endpoint
                if hasattr(browser, '_connection') and hasattr(browser._connection, '_transport'):
                    self.ws_endpoint = getattr(browser._connection._transport, '_ws_endpoint', None)
                elif hasattr(browser, 'new_browser_ws_endpoint'):
                    self.ws_endpoint = browser.new_browser_ws_endpoint()
                else:
                    # Try to extract from browser debug options if available
                    if hasattr(browser, '_impl_obj') and hasattr(browser._impl_obj, '_connection'):
                        conn = browser._impl_obj._connection
                        if hasattr(conn, '_transport') and hasattr(conn._transport, '_ws_endpoint'):
                            self.ws_endpoint = conn._transport._ws_endpoint
                        else:
                            self.ws_endpoint = None
                    else:
                        self.ws_endpoint = None
                        
                if self.ws_endpoint:
                    PrintStyle().print(f"CDP WebSocket endpoint captured: {self.ws_endpoint}")
                else:
                    PrintStyle().warning("CDP WebSocket endpoint not available - browser control may not work")
                    
            except (AttributeError, Exception) as e:
                PrintStyle().warning(f"Unable to capture CDP WebSocket endpoint: {e}")
                self.ws_endpoint = None
        
        # self.override_hooks()

        # Add init script to the browser session
        if self.browser_session and self.browser_session.browser_context:
            js_override = files.get_abs_path("lib/browser/init_override.js")
            await self.browser_session.browser_context.add_init_script(path=js_override) if self.browser_session else None

    def start_task(self, task: str):
        if self.task and self.task.is_alive():
            self.kill_task()

        self.task = defer.DeferredTask(
            thread_name="BrowserAgent" + self.agent.context.id
        )
        if self.agent.context.task:
            self.agent.context.task.add_child_task(self.task, terminate_thread=True)
        self.task.start_task(self._run_task, task) if self.task else None
        return self.task

    def kill_task(self):
        if self.task:
            self.task.kill(terminate_thread=True)
            self.task = None
        if self.browser_session:
            try:
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.browser_session.close()) if self.browser_session else None
                loop.close()
            except Exception as e:
                PrintStyle().error(f"Error closing browser session: {e}")
            finally:
                self.browser_session = None
        self.use_agent = None
        self.iter_no = 0

    async def _run_task(self, task: str):
        await self._initialize()

        class DoneResult(BaseModel):
            title: str
            response: str
            page_summary: str

        # Initialize controller
        controller = browser_use.Controller(output_model=DoneResult)

        # Register custom completion action with proper ActionResult fields
        @controller.registry.action("Complete task", param_model=DoneResult)
        async def complete_task(params: DoneResult):
            result = browser_use.ActionResult(
                is_done=True, success=True, extracted_content=params.model_dump_json()
            )
            return result

        model = self.agent.get_browser_model()

        try:

            secrets_manager = SecretsManager.get_instance()
            secrets_dict = secrets_manager.load_secrets()

            self.use_agent = browser_use.Agent(
                task=task,
                browser_session=self.browser_session,
                llm=model,
                use_vision=self.agent.config.browser_model.vision,
                extend_system_message=self.agent.read_prompt(
                    "prompts/browser_agent.system.md"
                ),
                controller=controller,
                enable_memory=False,  # Disable memory to avoid state conflicts
                sensitive_data=cast(dict[str, str | dict[str, str]] | None, secrets_dict or {}),  # Pass secrets
            )
        except Exception as e:
            raise Exception(
                f"Browser agent initialization failed. This might be due to model compatibility issues. Error: {e}"
            ) from e

        self.iter_no = get_iter_no(self.agent)

        async def hook(agent: browser_use.Agent):
            await self.agent.wait_if_paused()
            if self.iter_no != get_iter_no(self.agent):
                raise InterventionException("Task cancelled")

        # try:
        result = None
        if self.use_agent:
            result = await self.use_agent.run(
                max_steps=50, on_step_start=hook, on_step_end=hook
            )
        return result

    async def get_page(self):
        if self.use_agent and self.browser_session:
            try:
                return await self.use_agent.browser_session.get_current_page() if self.use_agent.browser_session else None
            except Exception:
                # Browser session might be closed or invalid
                return None
        return None

    async def get_selector_map(self):
        """Get the selector map for the current page state."""
        if self.use_agent:
            await self.use_agent.browser_session.get_state_summary(cache_clickable_elements_hashes=True) if self.use_agent.browser_session else None
            return await self.use_agent.browser_session.get_selector_map() if self.use_agent.browser_session else None
            await self.use_agent.browser_session.get_state_summary(
                cache_clickable_elements_hashes=True
            )
            return await self.use_agent.browser_session.get_selector_map()
        return {}

    async def hand_over_control(self):
        """
        Pause browser_use.Agent and expose control options for manual interaction.
        """
        # Prepare control options
        control_options = []
        msg_parts = ["🔎 Manual browser control requested.\n"]
        
        # CDP Control (for local development and Chrome DevTools)
        if self.ws_endpoint:
            ws_path = self.ws_endpoint.replace("ws://", "").replace("wss://", "")
            devtools_link = f"chrome-devtools://devtools/bundled/inspector.html?ws={ws_path}"
            control_options.append({
                "type": "cdp",
                "devtools_link": devtools_link,
                "ws_endpoint": self.ws_endpoint
            })
            msg_parts.extend([
                f"🌐 **DevTools Control (Recommended)**:",
                f"DevTools Link: {devtools_link}",
                "",
                "To use DevTools:",
                "1. Copy the DevTools link above",
                "2. Paste it into Chrome's address bar", 
                "3. Use DevTools to inspect and interact with the page",
                ""
            ])
        
        # VNC Control (for Docker containers)
        if self.vnc_url and self.display_port:
            control_options.append({
                "type": "vnc", 
                "vnc_url": self.vnc_url,
                "display_port": self.display_port
            })
            msg_parts.extend([
                f"🖥️ **VNC Control (Docker/Headless)**:",
                f"VNC URL: {self.vnc_url}",
                f"VNC Port: {self.display_port}",
                "",
                "To use VNC:",
                f"1. Connect with VNC client to localhost:{self.display_port}",
                "2. Or use web VNC at http://localhost:6080/vnc.html (if noVNC is setup)",
                "3. Interact directly with the browser window",
                ""
            ])
        
        if not control_options:
            msg = "❌ Browser control not available - no CDP or VNC endpoints found"
            PrintStyle().warning(msg)
            return {"error": msg}
        
        msg_parts.extend([
            "4. When finished, click the **Resume** button to continue automation",
            "",
            f"🔍 Environment: {'Docker' if self.is_docker else 'Local'}"
        ])
        
        msg = "\n".join(msg_parts)
        
        # Pause the agent - this will block wait_if_paused() calls
        self.agent.context.paused = True
        self.agent.hist_add_ai_response(msg)
        
        result = {
            "message": msg,
            "control_options": control_options,
            "environment": "docker" if self.is_docker else "local"
        }
        
        # Add primary control method for backward compatibility
        if control_options:
            primary = control_options[0]
            if primary["type"] == "cdp":
                result["devtools_link"] = primary["devtools_link"]
                result["ws_endpoint"] = primary["ws_endpoint"]
            elif primary["type"] == "vnc":
                result["vnc_url"] = primary["vnc_url"]
                result["display_port"] = primary["display_port"]
        
        return result


class BrowserAgent(Tool):

    async def execute(self, message="", reset="", takeover="", **kwargs):
        self.guid = str(uuid.uuid4())
        reset = str(reset).lower().strip() == "true"
        takeover = str(takeover).lower().strip() == "true"
        await self.prepare_state(reset=reset)
        
        # Check if user wants to take manual control
        if takeover and self.state:
            control_result = await self.state.hand_over_control()
            if control_result:
                return Response(
                    message=control_result["message"],
                    break_loop=False,
                )
        
        task = self.state.start_task(message) if self.state else None

        # wait for browser agent to finish and update progress with timeout
        timeout_seconds = 300  # 5 minute timeout
        start_time = time.time()

        fail_counter = 0
        while not task.is_ready() if task else False:
            # Check for timeout to prevent infinite waiting
            if time.time() - start_time > timeout_seconds:
                PrintStyle().warning(
                    self._mask(f"Browser agent task timeout after {timeout_seconds} seconds, forcing completion")
                )
                break

            await self.agent.handle_intervention()
            await asyncio.sleep(1)
            try:
                if task and task.is_ready():  # otherwise get_update hangs
                    break
                try:
                    update = await asyncio.wait_for(self.get_update(), timeout=10)
                    fail_counter = 0  # reset on success
                except asyncio.TimeoutError:
                    fail_counter += 1
                    PrintStyle().warning(
                        self._mask(f"browser_agent.get_update timed out ({fail_counter}/3)")
                    )
                    if fail_counter >= 3:
                        PrintStyle().warning(
                            self._mask("3 consecutive browser_agent.get_update timeouts, breaking loop")
                        )
                        break
                    continue
                update_log = update.get("log", get_use_agent_log(None))
                self.update_progress("\n".join(update_log))
                screenshot = update.get("screenshot", None)
                if screenshot:
                    self.log.update(screenshot=screenshot)
            except Exception as e:
                PrintStyle().error(self._mask(f"Error getting update: {str(e)}"))

        if task and not task.is_ready():
            PrintStyle().warning(self._mask("browser_agent.get_update timed out, killing the task"))
            self.state.kill_task() if self.state else None
            return Response(
                message=self._mask("Browser agent task timed out, not output provided."),
                break_loop=False,
            )

        # final progress update
        if self.state and self.state.use_agent:
            log_final = get_use_agent_log(self.state.use_agent)
            self.update_progress("\n".join(log_final))

        # collect result with error handling
        try:
            result = await task.result() if task else None
        except Exception as e:
            PrintStyle().error(self._mask(f"Error getting browser agent task result: {str(e)}"))
            # Return a timeout response if task.result() fails
            answer_text = self._mask(f"Browser agent task failed to return result: {str(e)}")
            self.log.update(answer=answer_text)
            return Response(message=answer_text, break_loop=False)
        # finally:
        #     # Stop any further browser access after task completion
        #     # self.state.kill_task()
        #     pass

        # Check if task completed successfully
        if result and result.is_done():
            answer = result.final_result()
            try:
                if answer and isinstance(answer, str) and answer.strip():
                    answer_data = DirtyJson.parse_string(answer)
                    answer_text = strings.dict_to_text(answer_data)  # type: ignore
                else:
                    answer_text = (
                        str(answer) if answer else "Task completed successfully"
                    )
            except Exception as e:
                answer_text = (
                    str(answer)
                    if answer
                    else f"Task completed with parse error: {str(e)}"
                )
        else:
            # Task hit max_steps without calling done()
            urls = result.urls() if result else []
            current_url = urls[-1] if urls else "unknown"
            answer_text = (
                f"Task reached step limit without completion. Last page: {current_url}. "
                f"The browser agent may need clearer instructions on when to finish."
            )

        # Mask answer for logs and response
        answer_text = self._mask(answer_text)

        # update the log (without screenshot path here, user can click)
        self.log.update(answer=answer_text)

        # add screenshot to the answer if we have it
        if (
            self.log.kvps
            and "screenshot" in self.log.kvps
            and self.log.kvps["screenshot"]
        ):
            path = self.log.kvps["screenshot"].split("//", 1)[-1].split("&", 1)[0]
            answer_text += f"\n\nScreenshot: {path}"

        # respond (with screenshot path)
        return Response(message=answer_text, break_loop=False)

    def get_log_object(self):
        return self.agent.context.log.log(
            type="browser",
            heading=f"icon://captive_portal {self.agent.agent_name}: Calling Browser Agent",
            content="",
            kvps=self.args,
        )

    async def get_update(self):
        await self.prepare_state()

        result = {}
        agent = self.agent
        ua = self.state.use_agent if self.state else None
        page = await self.state.get_page() if self.state else None

        if ua and page:
            try:

                async def _get_update():

                    # await agent.wait_if_paused() # no need here

                    # Build short activity log
                    result["log"] = get_use_agent_log(ua)

                    path = files.get_abs_path(
                        persist_chat.get_chat_folder_path(agent.context.id),
                        "browser",
                        "screenshots",
                        f"{self.guid}.png",
                    )
                    files.make_dirs(path)
                    await page.screenshot(path=path, full_page=False, timeout=3000)
                    result["screenshot"] = f"img://{path}&t={str(time.time())}"

                if self.state and self.state.task and not self.state.task.is_ready():
                    await self.state.task.execute_inside(_get_update)

            except Exception:
                pass

        return result

    async def prepare_state(self, reset=False):
        self.state = self.agent.get_data("_browser_agent_state")
        if reset and self.state:
            self.state.kill_task()
        if not self.state or reset:
            self.state = await State.create(self.agent)
        self.agent.set_data("_browser_agent_state", self.state)

    def update_progress(self, text):
        text = self._mask(text)
        short = text.split("\n")[-1]
        if len(short) > 50:
            short = short[:50] + "..."
        progress = f"Browser: {short}"

        self.log.update(progress=text)
        self.agent.context.log.set_progress(progress)

    def _mask(self, text: str) -> str:
        try:
            return SecretsManager.get_instance().mask_values(text or "")
        except Exception as e:
            return text or ""

    # def __del__(self):
    #     if self.state:
    #         self.state.kill_task()


def get_use_agent_log(use_agent: browser_use.Agent | None):
    result = ["🚦 Starting task"]
    if use_agent:
        action_results = use_agent.state.history.action_results()
        short_log = []
        for item in action_results:
            # final results
            if item.is_done:
                if item.success:
                    short_log.append("✅ Done")
                else:
                    short_log.append(
                        f"❌ Error: {item.error or item.extracted_content or 'Unknown error'}"
                    )

            # progress messages
            else:
                text = item.extracted_content
                if text:
                    first_line = text.split("\n", 1)[0][:200]
                    short_log.append(first_line)
        result.extend(short_log)
    return result
