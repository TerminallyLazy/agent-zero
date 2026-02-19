from python.helpers.api import ApiHandler, Input, Output, Request


class StomperSettings(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        from plugins.prompt_stomper.helpers.stomper_settings import get_settings, set_settings

        if request.method == "GET" or not input:
            return {"settings": get_settings()}

        # POST: update settings
        updates = input.get("settings", input)
        updated = set_settings(updates)
        return {"settings": updated}

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
