from agent import Agent, UserMessage
import asyncio
import time
import re
from python.helpers.tool import Tool, Response
from python.tools.code_execution_tool import CodeExecution

class SweOrchestrator(Tool):
    async def execute(self, **kwargs) -> Response:
        tasks = self.args.get("tasks", [])
        max_parallel = int(self.args.get("max_parallel", 3))
        stop_on_error = str(self.args.get("stop_on_error", "false")).lower().strip() == "true"
        allow_write_tools = str(self.args.get("allow_write_tools", "false")).lower().strip() == "true"
        dry_run = str(self.args.get("dry_run", "true")).lower().strip() == "true"
        fasta2a_enabled = str(self.args.get("fasta2a_enabled", "false")).lower().strip() == "true"

        if not isinstance(tasks, list) or not tasks:
            return Response(message="No tasks provided.", break_loop=False)

        plan = []
        for i, t in enumerate(tasks):
            kind = t.get("kind", "subordinate")
            profile = t.get("prompt_profile", "swe-agent")
            timeout = t.get("timeout", 600)
            cwd = t.get("cwd", ".")
            plan.append(f"[{i}] kind={kind} profile={profile} timeout={timeout} cwd={cwd}")
        if dry_run:
            return Response(message="Planned async batch:\n" + "\n".join(plan), break_loop=False)

        sem = asyncio.Semaphore(max_parallel)

        async def run_one(idx, t):
            async with sem:
                kind = t.get("kind", "subordinate")
                start = time.time()
                try:
                    if fasta2a_enabled:
                        pass
                    if kind == "subordinate":
                        msg = t.get("message", "")
                        profile = t.get("prompt_profile", "swe-agent")
                        timeout = int(t.get("timeout", 600))
                        retries = int(t.get("retries", 0))
                        attempt = 0
                        last_exc = None
                        while attempt <= retries:
                            try:
                                sub = Agent(self.agent.number + 1, self.agent.config, self.agent.context)
                                sub.set_data(Agent.DATA_NAME_SUPERIOR, self.agent)
                                sub.config.prompts_subdir = profile
                                if msg:
                                    sub.hist_add_user_message(UserMessage(message=msg, attachments=[]))
                                out = await asyncio.wait_for(sub.monologue(), timeout=timeout)
                                dur = time.time() - start
                                output = str(out) if out is not None else ""
                                return {"index": idx, "kind": kind, "ok": True, "duration": dur, "output": output[:2000]}
                            except Exception as e:
                                last_exc = e
                                attempt += 1
                        raise last_exc or RuntimeError("Subordinate task failed")
                    elif kind == "terminal":
                        code = t.get("code", "")
                        timeout = int(t.get("timeout", 600))
                        if not allow_write_tools:
                            if re.search(r"(?:\brm\b|\bchmod\b|\bchown\b|\bmv\b|\bcp\b\s+-[rR]|\>|\bgit\s+push\b)", code):
                                raise PermissionError("terminal task denied: potential write/destructive command and allow_write_tools is false")
                        args = {"runtime": "terminal", "code": code, "session": 0}
                        cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
                        cet.log = self.get_log_object()
                        out = await asyncio.wait_for(cet.execute(**args), timeout=timeout)
                        dur = time.time() - start
                        msg = out.message if hasattr(out, "message") else ""
                        return {"index": idx, "kind": kind, "ok": True, "duration": dur, "output": msg[:2000]}
                    else:
                        raise ValueError(f"Unsupported task kind: {kind}")
                except Exception as e:
                    dur = time.time() - start
                    return {"index": idx, "kind": kind, "ok": False, "duration": dur, "error": str(e)[:500]}

        coros = [run_one(i, t) for i, t in enumerate(tasks)]
        settled = await asyncio.gather(*coros, return_exceptions=False)

        lines = ["Async orchestration results:"]
        errors = 0
        for r in settled:
            if not r["ok"]:
                errors += 1
                lines.append(f"[{r['index']}] {r['kind']} - ERROR in {r['duration']:.2f}s: {r.get('error','')}")
            else:
                lines.append(f"[{r['index']}] {r['kind']} - OK in {r['duration']:.2f}s")
                out = r.get("output", "")
                if out:
                    preview_lines = out.splitlines()
                    preview = preview_lines[:10]
                    lines.extend([f"    {p}" for p in preview])
                    more = max(0, len(preview_lines) - 10)
                    if more:
                        lines.append(f"    ... (+{more} more lines)")
        if stop_on_error and errors:
            lines.append(f"Stopped on error(s): {errors}")
        return Response(message="\n".join(lines), break_loop=False)
