import asyncio
import os
import sys
import tempfile
import subprocess
from typing import Dict, Any

from helpers.tool import Tool, Response


class CodeExecution(Tool):
    """
    Tool for executing code locally.
    """
    async def execute(self, **kwargs):
        await self.agent.handle_intervention()  # Handle any pending interventions
        
        runtime = self.args.get("runtime", "").lower().strip()
        session = int(self.args.get("session", 0))
        
        if runtime == "python":
            response = await self.execute_python_code(
                code=self.args["code"], session=session
            )
        elif runtime == "terminal":
            response = await self.execute_terminal_command(
                command=self.args["code"], session=session
            )
        else:
            response = f"Unsupported runtime: {runtime}. Please use 'python' or 'terminal'."
        
        if not response:
            response = "No output was produced."
        
        return Response(message=response, break_loop=False)
    
    async def execute_python_code(self, code: str, session: int = 0) -> str:
        """
        Execute Python code and return the output.
        """
        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # Execute the code and capture output
            process = await asyncio.create_subprocess_exec(
                sys.executable, temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Prepare the response
            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                if output:
                    output += "\n\n"
                output += "Error:\n" + stderr.decode("utf-8", errors="replace")
            
            return output
        except Exception as e:
            return f"Error executing Python code: {str(e)}"
        finally:
            # Clean up the temporary file
            try:
                os.unlink(temp_file)
            except:
                pass
    
    async def execute_terminal_command(self, command: str, session: int = 0) -> str:
        """
        Execute a terminal command and return the output.
        """
        try:
            # Execute the command in a shell and capture output
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )
            
            stdout, stderr = await process.communicate()
            
            # Prepare the response
            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                if output:
                    output += "\n\n"
                output += "Error:\n" + stderr.decode("utf-8", errors="replace")
            
            return output
        except Exception as e:
            return f"Error executing terminal command: {str(e)}"