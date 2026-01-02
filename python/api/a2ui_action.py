from agent import AgentContext, UserMessage
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.print_style import PrintStyle


class A2uiAction(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        action_id = input.get("actionId", "")
        surface_id = input.get("surfaceId", "")
        component_id = input.get("componentId", "")
        context_data = input.get("context", {})
        ctxid = input.get("ctxid", "")

        if not action_id:
            return Response("actionId is required", status=400)

        context = self.use_context(ctxid)

        action_message = self._format_action_message(
            action_id=action_id,
            surface_id=surface_id,
            component_id=component_id,
            context_data=context_data,
        )

        PrintStyle(
            background_color="#1E88E5", font_color="white", bold=True, padding=True
        ).print(f"A2UI Action: {action_id}")
        PrintStyle(font_color="white", padding=False).print(f"> {action_message}")

        context.log.log(
            type="info",
            heading=f"A2UI Action: {action_id}",
            content=action_message,
            kvps={
                "actionId": action_id,
                "surfaceId": surface_id,
                "componentId": component_id,
            },
        )

        task = context.communicate(UserMessage(action_message, []))

        return {
            "status": "accepted",
            "actionId": action_id,
            "ctxid": context.id,
        }

    def _format_action_message(
        self,
        action_id: str,
        surface_id: str,
        component_id: str,
        context_data: dict,
    ) -> str:
        parts = [f"[A2UI_ACTION:{action_id}]"]

        if component_id:
            parts.append(f"Component: {component_id}")

        if surface_id:
            parts.append(f"Surface: {surface_id}")

        if context_data:
            parts.append(f"Data: {context_data}")

        return " | ".join(parts)
