"""Inject Context Engine behavioural guidance into the agent system prompt.

Tells the agent what Context Engine tools are available and when to use them.
Only active when the context-engine plugin is enabled.
"""

from python.helpers.extension import Extension
from python.helpers import plugins
from agent import LoopData

BEHAVIOUR_PROMPT = """## Context Engine — code search and developer memory

You have access to Context Engine tools for deep codebase understanding:

**Code search and analysis:**
- `code_search` — semantic search across the indexed codebase. Use when you need to find relevant code snippets, functions, or classes by describing what you're looking for in natural language.
- `context_answer` — ask questions about the codebase and get AI-generated answers grounded in actual code with citations. Use when the user asks how something works or you need to understand code behaviour.
- `symbol_graph` — map relationships between symbols (callers, callees, importers). Use to trace dependencies before refactoring or to understand how a function fits into the larger system.
- `context_index` — index a directory so it becomes searchable. Run this before searching a directory that hasn't been indexed yet.

**Developer memory:**
- `ce_memory_store` — save development knowledge, decisions, and findings for future reference.
- `ce_memory_find` — search previously stored knowledge by semantic query.

**Specialized searches:**
- `search_tests` — find test files related to a given function or class.
- `search_callers` — find all call sites of a function or class across the codebase.

**When to use these tools:**
- Use `code_search` before making changes to unfamiliar code — find relevant files first.
- Use `context_answer` when you need an explanation of how a subsystem works.
- Use `symbol_graph` before refactoring to understand impact.
- Use `context_index` when the user points you to a new project or directory.
- Store important findings with `ce_memory_store` so they persist across conversations.
"""


class ContextEngineBehaviour(Extension):

    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        config = plugins.get_plugin_config("context-engine", self.agent)
        if not config:
            return

        system_prompt.append(BEHAVIOUR_PROMPT)
