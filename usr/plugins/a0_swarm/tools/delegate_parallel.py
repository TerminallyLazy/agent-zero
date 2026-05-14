from __future__ import annotations
import asyncio
import logging

from agent import AgentContext, UserMessage
from helpers import plugins
from helpers.tool import Tool, Response
from initialize import initialize_agent
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgent, SwarmAgentStatus, MAX_RESULT_BYTES, utc_iso_now,
)

logger = logging.getLogger(__name__)


def _load_cfg(agent) -> dict:
    try:
        return plugins.get_plugin_config("a0_swarm", agent=agent) or {}
    except Exception:
        return {}


class DelegateParallel(Tool):
    async def execute(self, tasks: list | None = None, **kwargs):
        if not tasks:
            return Response(
                message="No tasks provided to delegate_parallel.",
                break_loop=False,
            )

        cfg = _load_cfg(self.agent)
        max_parallel = int(cfg.get("max_parallel") or 0)
        default_profile = (cfg.get("default_profile") or "").strip()
        result_kb_cap = int(cfg.get("result_kb_cap") or 0)
        self._result_byte_cap = (result_kb_cap * 1024) if result_kb_cap > 0 else MAX_RESULT_BYTES

        if max_parallel > 0 and len(tasks) > max_parallel:
            return Response(
                message=(
                    f"delegate_parallel rejected: requested {len(tasks)} tasks "
                    f"but plugin setting max_parallel={max_parallel}."
                ),
                break_loop=False,
            )
        if max_parallel == 0 and len(tasks) > 16:
            logger.warning(
                "delegate_parallel: large fan-out (%d tasks); no cap enforced.",
                len(tasks),
            )

        registry = SwarmRegistry.get()
        parent_ctx_id = self.agent.context.id
        entries: list[SwarmAgent] = []
        coros = []

        for i, td in enumerate(tasks):
            label = td.get("label", f"Agent-{i+1}")
            task_text = td.get("task", "")
            profile = td.get("profile", "") or default_profile

            config = initialize_agent()
            if profile:
                config.profile = profile

            sub_ctx = AgentContext(config=config)
            sub_agent = sub_ctx.agent0
            agent_name = f"SA{self.agent.number + 1}_{i+1}"
            sub_agent.agent_name = agent_name

            entry = SwarmAgent(
                agent_name=agent_name,
                label=label,
                task=task_text,
                context_id=sub_ctx.id,
                parent_context_id=parent_ctx_id,
                status=SwarmAgentStatus.PENDING,
                started_at=utc_iso_now(),
            )
            registry.register(entry)
            entries.append(entry)
            coros.append(self._run_subagent(sub_ctx, sub_agent, task_text, entry))

        results = await asyncio.gather(*coros, return_exceptions=True)
        return Response(message=self._summarize(entries, results), break_loop=False)

    async def _run_subagent(self, sub_ctx, sub_agent, task_text, entry):
        registry = SwarmRegistry.get()
        registry.update_status(entry.agent_name, SwarmAgentStatus.WORKING)
        try:
            sub_agent.hist_add_user_message(UserMessage(message=task_text))
            result = await sub_agent.monologue()
            raw = (result or "")
            encoded = raw.encode("utf-8")
            cap = getattr(self, "_result_byte_cap", MAX_RESULT_BYTES)
            if len(encoded) > cap:
                stored = encoded[:cap].decode("utf-8", errors="ignore") + "\n[...truncated]"
            else:
                stored = raw
            registry.update_status(
                entry.agent_name, SwarmAgentStatus.DONE,
                result=stored, current_activity="",
            )
            return result or ""
        except Exception as e:
            registry.update_status(
                entry.agent_name, SwarmAgentStatus.FAILED,
                blocker=str(e)[:2000], current_activity="",
            )
            raise
        finally:
            try:
                AgentContext.remove(sub_ctx.id)
            except Exception:
                pass

    def _summarize(self, entries, results) -> str:
        parts = []
        for entry, result in zip(entries, results):
            if isinstance(result, Exception):
                parts.append(
                    f"### {entry.label} ({entry.agent_name})\n"
                    f"**Status:** FAILED\n**Error:** {result}\n"
                )
            else:
                parts.append(
                    f"### {entry.label} ({entry.agent_name})\n"
                    f"**Status:** DONE\n**Result:**\n{result}\n"
                )
        return (
            f"## Parallel Delegation Complete\n"
            f"{len(entries)} agents ran. Results:\n\n"
            + "\n---\n".join(parts)
        )

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://group_work {self.agent.agent_name}: Delegating Parallel Tasks",
            content="",
            kvps=self.args,
        )
