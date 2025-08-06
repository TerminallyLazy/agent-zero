import asyncio
from dataclasses import dataclass
import shlex
import time
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers.shell_local import LocalInteractiveSession
import re


@dataclass
class State:
    shells: dict[int, LocalInteractiveSession]


class CodeExecution(Tool):

    async def execute(self, **kwargs):
        await self.agent.handle_intervention()  # wait for intervention and handle it, if paused

        await self.prepare_state()

        runtime = self.args.get("runtime", "").lower().strip()
        session = int(self.args.get("session", 0))
        code = self.args.get("code", "")

        if runtime == "python":
            response = await self.execute_python_code(code=code, session=session)
        elif runtime == "nodejs":
            response = await self.execute_nodejs_code(code=code, session=session)
        elif runtime == "terminal":
            response = await self.execute_terminal_command(command=code, session=session)
        elif runtime == "output":
            response = await self.get_terminal_output(session=session)
        else:
            response = Response(
                message=f"Unknown runtime: {runtime}. Supported: python, nodejs, terminal, output",
                break_loop=False,
            )

        return response

    async def prepare_state(self):
        state = self.agent.get_data("code_exec_state")
        if state is None:
            state = State(shells={})
            self.agent.set_data("code_exec_state", state)
        self.state = state

    async def get_or_create_shell(self, session: int) -> LocalInteractiveSession:
        if session not in self.state.shells:
            shell = LocalInteractiveSession()
            await shell.connect()
            self.state.shells[session] = shell
            PrintStyle(font_color="cyan").print(f"Created new local shell session {session}")
        
        return self.state.shells[session]

    async def execute_python_code(self, code: str, session: int):
        self.log_execution("Python", code)
        shell = await self.get_or_create_shell(session)
        
        # Execute Python code using python3 -c
        escaped_code = shlex.quote(code)
        command = f"python3 -c {escaped_code}"
        
        shell.send_command(command)
        await asyncio.sleep(0.5)  # Give time for execution
        
        output, _ = await shell.read_output(timeout=3)
        return self.create_response(output, "Python code executed")

    async def execute_nodejs_code(self, code: str, session: int):
        self.log_execution("Node.js", code)
        shell = await self.get_or_create_shell(session)
        
        # Execute Node.js code using node -e
        escaped_code = shlex.quote(code)
        command = f"node -e {escaped_code}"
        
        shell.send_command(command)
        await asyncio.sleep(0.5)  # Give time for execution
        
        output, _ = await shell.read_output(timeout=3)
        return self.create_response(output, "Node.js code executed")

    async def execute_terminal_command(self, command: str, session: int):
        self.log_execution("Terminal", command)
        shell = await self.get_or_create_shell(session)
        
        shell.send_command(command)
        await asyncio.sleep(0.2)  # Give time for command to start
        
        output, _ = await shell.read_output(timeout=3)
        return self.create_response(output, "Command executed")

    async def get_terminal_output(self, session: int, timeout: float = 5):
        if session not in self.state.shells:
            return Response(message=f"No shell session {session} found", break_loop=False)
        
        shell = self.state.shells[session]
        output, _ = await shell.read_output(timeout=timeout)
        
        if output:
            return self.create_response(output, "Output retrieved")
        else:
            return Response(message="No new output", break_loop=False)

    def create_response(self, output: str, prefix: str = "") -> Response:
        # Clean ANSI escape codes
        output = self.clean_ansi(output)
        
        # Trim output if too long
        max_length = 10000
        if len(output) > max_length:
            output = output[:max_length] + "\n... (output truncated)"
        
        if output.strip():
            message = f"{prefix}:\n\n{output}" if prefix else output
        else:
            message = f"{prefix} (no output)" if prefix else "Command executed (no output)"
        
        return Response(message=message, break_loop=False)

    def clean_ansi(self, text: str) -> str:
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def log_execution(self, runtime: str, code: str):
        PrintStyle(background_color="white", font_color="#1B4F72", bold=True).print(
            f"{self.agent.agent_name}: Executing {runtime} code"
        )
        # Show first 500 chars of code
        display_code = code[:500] + ("..." if len(code) > 500 else "")
        PrintStyle(font_color="cyan").print(display_code)

    async def before_execution(self, **kwargs):
        await super().before_execution(**kwargs)

    async def after_execution(self, response: Response, **kwargs):
        await super().after_execution(response, **kwargs)