from dataclasses import asdict
from helpers.api import ApiHandler, Request

from usr.plugins.dj_booth.helpers.state import get_state


class StreamStatus(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict:
        return asdict(get_state())
