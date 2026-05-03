"""Inject current dj_booth stream state into the agent system prompt."""
from typing import Any
from helpers.extension import Extension


class DjContext(Extension):
    async def execute(self, system_prompt: list[str] = [], **kwargs: Any):
        try:
            from usr.plugins.dj_booth.helpers.state import get_state
            s = get_state()
            if not s.is_running:
                return
            block = (
                "## DJ Booth Status\n"
                f"- Stream: {s.stream_url} (engine={s.engine}, {s.listener_count} listeners)\n"
                f"- Now playing: {s.current_track or '(silence)'}\n"
                f"- Queue: {len(s.queue)} tracks\n"
                f"- Library: {s.library_count} tracks scanned\n"
            )
            system_prompt.append(block)
        except Exception:
            return
