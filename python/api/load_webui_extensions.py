from python.helpers.api import ApiHandler, Request, Response
from python.helpers import plugins


class LoadWebuiExtensions(ApiHandler):
    """
    API endpoint for Welcome Screen banners.
    Add checks as extension scripts in python/extensions/banners/ or usr/extensions/banners/
    """

    async def process(self, input: dict, request: Request) -> dict | Response:
        extension_point = input.get("extension_point", [])
        filters = input.get("filters", [])

        if not extension_point:
            return Response(status=400, response="Missing extension_point")
        
        exts = plugins.get_webui_extensions(extension_point, filters)
        
        return {"extensions": exts or []}
