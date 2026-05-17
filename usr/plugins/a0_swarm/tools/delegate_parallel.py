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
from usr.plugins.a0_swarm.helpers import a2a_runner
from usr.plugins.a0_swarm.helpers.remotes import RemoteEndpoint, resolve_endpoint

logger = logging.getLogger(__name__)


def _load_cfg(agent) -> dict:
    try:
        return plugins.get_plugin_config("a0_swarm", agent=agent) or {}
    except Exception:
        return {}


# Map A2A terminal state strings to our SwarmAgentStatus.
_A2A_TERMINAL_MAP = {
    "completed":  SwarmAgentStatus.DONE,
    "failed":     SwarmAgentStatus.FAILED,
    "canceled":   SwarmAgentStatus.CANCELLED,
    "cancelled":  SwarmAgentStatus.CANCELLED,
    "timeout":    SwarmAgentStatus.FAILED,
}


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
        run = registry.create_run(
            parent_context_id=parent_ctx_id,
            parent_agent_name=getattr(self.agent, "agent_name", "orchestrator"),
            title=f"delegate_parallel: {len(tasks)} task(s)",
        )
        entries: list[SwarmAgent] = []
        coros = []

        for i, td in enumerate(tasks):
            label = td.get("label", f"Agent-{i+1}")
            task_text = td.get("task", "")
            profile = td.get("profile", "") or default_profile
            endpoint = (td.get("endpoint") or "").strip()
            agent_name = f"SA{self.agent.number + 1}_{i+1}"

            if endpoint:
                remote = resolve_endpoint(endpoint, agent=self.agent)
                if remote is None:
                    # Unknown remote — record an immediately-failed entry
                    entry = SwarmAgent(
                        agent_name=agent_name, label=label, task=task_text,
                        context_id="", parent_context_id=parent_ctx_id,
                        status=SwarmAgentStatus.FAILED,
                        started_at=utc_iso_now(),
                        blocker=f"Unknown remote endpoint: {endpoint}",
                        remote_label=endpoint,
                        run_id=run.run_id,
                        delivery_mode="remote_a2a",
                    )
                    registry.register(entry)
                    entries.append(entry)
                    coros.append(asyncio.sleep(0))   # placeholder
                    continue

                entry = SwarmAgent(
                    agent_name=agent_name, label=label, task=task_text,
                    context_id="", parent_context_id=parent_ctx_id,
                    status=SwarmAgentStatus.PENDING,
                    started_at=utc_iso_now(),
                    remote_label=remote.label,
                    remote_base_url=remote.base_url,
                    remote_auth_token=remote.auth_token,
                    run_id=run.run_id,
                    delivery_mode="remote_a2a",
                )
                registry.register(entry)
                entries.append(entry)
                coros.append(self._run_remote(remote, task_text, entry))
                continue

            # Local subagent path.
            config = initialize_agent()
            if profile:
                config.profile = profile
            sub_ctx = AgentContext(config=config)
            sub_agent = sub_ctx.agent0
            sub_agent.agent_name = agent_name

            entry = SwarmAgent(
                agent_name=agent_name, label=label, task=task_text,
                context_id=sub_ctx.id, parent_context_id=parent_ctx_id,
                status=SwarmAgentStatus.PENDING,
                started_at=utc_iso_now(),
                run_id=run.run_id,
                delivery_mode="local",
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
            stored = self._cap_result(result or "")
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

    async def _run_remote(self, remote: RemoteEndpoint, task_text: str, entry: SwarmAgent):
        registry = SwarmRegistry.get()
        if not a2a_runner.is_available():
            registry.update_status(
                entry.agent_name, SwarmAgentStatus.FAILED,
                blocker="FastA2A client not available in this Agent Zero build.",
            )
            raise RuntimeError("FastA2A client not available")

        registry.update_status(
            entry.agent_name, SwarmAgentStatus.WORKING,
            current_activity=f"Submitting to {remote.label}",
        )
        try:
            conn, task_id, remote_ctx_id = await a2a_runner.submit_task(remote, task_text)
        except Exception as e:
            registry.update_status(
                entry.agent_name, SwarmAgentStatus.FAILED,
                blocker=f"Could not reach {remote.label}: {e}",
            )
            raise

        # Persist task_id + remote context so cancel/intervene can target it.
        registry.update_status(
            entry.agent_name,
            SwarmAgentStatus.WORKING,
            current_activity=f"Running on {remote.label}",
            remote_task_id=task_id,
            context_id=remote_ctx_id,
        )

        try:
            state, result_text = await a2a_runner.wait_for_result(conn, task_id)
        finally:
            try:
                await conn.close()
            except Exception:
                pass

        mapped = _A2A_TERMINAL_MAP.get(state, SwarmAgentStatus.FAILED)
        if mapped is SwarmAgentStatus.DONE:
            stored = self._cap_result(result_text)
            registry.update_status(
                entry.agent_name, SwarmAgentStatus.DONE,
                result=stored, current_activity="",
            )
            return result_text
        else:
            registry.update_status(
                entry.agent_name, mapped,
                blocker=result_text[:2000] if result_text else f"Remote state: {state}",
                current_activity="",
            )
            if mapped is SwarmAgentStatus.FAILED:
                raise RuntimeError(result_text or f"Remote task ended in state {state}")
            return result_text

    def _cap_result(self, raw: str) -> str:
        encoded = raw.encode("utf-8")
        cap = getattr(self, "_result_byte_cap", MAX_RESULT_BYTES)
        if len(encoded) > cap:
            return encoded[:cap].decode("utf-8", errors="ignore") + "\n[...truncated]"
        return raw

    def _summarize(self, entries, results) -> str:
        parts = []
        for entry, result in zip(entries, results):
            origin = f" via {entry.remote_label}" if entry.is_remote else ""
            if isinstance(result, Exception):
                parts.append(
                    f"### {entry.label} ({entry.agent_name}){origin}\n"
                    f"**Status:** FAILED\n**Error:** {result}\n"
                )
            else:
                parts.append(
                    f"### {entry.label} ({entry.agent_name}){origin}\n"
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
