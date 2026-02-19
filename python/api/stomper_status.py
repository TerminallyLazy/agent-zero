from python.helpers.api import ApiHandler, Input, Output, Request


class StomperStatus(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        from plugins.prompt_stomper.helpers.stomper_log import get_stomper_log
        from plugins.prompt_stomper.helpers.stomper_settings import get_settings

        settings = get_settings()
        log = get_stomper_log()
        stats = log.get_stats()

        return {
            "enabled": settings.get("enabled", True),
            "stats": stats,
            "settings": settings,
        }

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
