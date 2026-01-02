from python.helpers.tool import Tool, Response
from python.helpers.a2ui_validator import validate_component, A2UIValidationError
import json


class A2UIComponentTool(Tool):
    async def execute(self, **kwargs) -> Response:
        if not getattr(self.agent.config, "a2ui_enabled", True):
            fallback = self.args.get("fallback_text", "A2UI components are disabled")
            return Response(message=fallback, break_loop=False)

        surface_id = self.args.get("surface_id", f"surface_{self.agent.number}")
        messages = self.args.get("messages", None)
        components = self.args.get("components", None)
        data_model = self.args.get("data_model", None)
        fallback_text = self.args.get("fallback_text", "")
        break_loop = self.args.get("break_loop", False)

        if messages:
            a2ui_messages = messages
        elif components:
            a2ui_messages = self._build_messages(surface_id, components, data_model)
        else:
            return Response(
                message="Error: either 'messages' or 'components' is required",
                break_loop=False,
            )

        for msg in a2ui_messages:
            if "surfaceUpdate" in msg:
                for comp in msg["surfaceUpdate"].get("components", []):
                    if "component" in comp:
                        try:
                            validate_component(comp["component"], strict=False)
                        except A2UIValidationError as e:
                            self.agent.context.log.log(
                                type="hint",
                                heading=f"{self.agent.agent_name}: A2UI Warning",
                                content=f"Component validation note: {e}",
                            )

        self.agent.context.log.log(
            type="a2ui",
            id=surface_id,
            heading=f"icon://widgets {self.agent.agent_name}: UI Component",
            content=fallback_text,
            kvps={
                "messages": a2ui_messages,
                "surface_id": surface_id,
                "fallback": fallback_text,
            },
        )

        return Response(
            message=fallback_text,
            break_loop=break_loop,
            additional={"a2ui_surface_id": surface_id},
        )

    def _build_messages(
        self, surface_id: str, components: list, data_model: dict | None
    ) -> list:
        messages = []

        root_id = None
        for comp in components:
            if comp.get("id") == "root" or root_id is None:
                root_id = comp.get("id", "root")

        messages.append(
            {"surfaceUpdate": {"surfaceId": surface_id, "components": components}}
        )

        if data_model:
            contents = self._dict_to_contents(data_model)
            messages.append(
                {"dataModelUpdate": {"surfaceId": surface_id, "contents": contents}}
            )

        messages.append({"beginRendering": {"surfaceId": surface_id, "root": root_id}})

        return messages

    def _dict_to_contents(self, data: dict) -> list:
        contents = []
        for key, value in data.items():
            if isinstance(value, str):
                contents.append({"key": key, "valueString": value})
            elif isinstance(value, bool):
                contents.append({"key": key, "valueBoolean": value})
            elif isinstance(value, (int, float)):
                contents.append({"key": key, "valueNumber": value})
            elif isinstance(value, dict):
                contents.append({"key": key, "valueMap": self._dict_to_contents(value)})
            elif isinstance(value, list):
                list_contents = []
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        list_contents.append(
                            {"key": str(i), "valueMap": self._dict_to_contents(item)}
                        )
                    elif isinstance(item, str):
                        list_contents.append({"key": str(i), "valueString": item})
                    elif isinstance(item, (int, float)):
                        list_contents.append({"key": str(i), "valueNumber": item})
                contents.append({"key": key, "valueMap": list_contents})
        return contents

    async def before_execution(self, **kwargs):
        pass

    async def after_execution(self, response: Response, **kwargs):
        self.agent.hist_add_tool_result(
            self.name,
            response.message,
            **(response.additional or {}),
        )
