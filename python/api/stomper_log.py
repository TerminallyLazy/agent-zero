from python.helpers.api import ApiHandler, Input, Output, Request


class StomperLog(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        from plugins.prompt_stomper.helpers.stomper_log import get_stomper_log

        log = get_stomper_log()

        action = input.get("action", "get")

        if action == "clear":
            log.clear()
            return {"status": "cleared"}

        limit = input.get("limit", 50)
        offset = input.get("offset", 0)
        min_severity = input.get("min_severity", 0)

        events = log.get_events(limit=limit, offset=offset, min_severity=min_severity)
        stats = log.get_stats()

        return {"events": events, "stats": stats}

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]
