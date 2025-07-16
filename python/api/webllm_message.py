from agent import AgentContext
from python.helpers.api import ApiHandler
from flask import Request, Response
from models import ModelProvider, WebLLMChatWrapper
from python.helpers.print_style import PrintStyle
import json


class WebllmMessage(ApiHandler):
    """
    API handler for WebLLM client-side inference.
    This endpoint receives messages intended for WebLLM processing.
    """
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            # Extract message data
            text = input.get("text", "")
            ctxid = input.get("context", "")
            model_name = input.get("model", "")
            system_prompt = input.get("system", "")
            
            if not text:
                return {"error": "No message text provided"}
            
            if not model_name:
                return {"error": "No WebLLM model specified"}
            
            # Get agent context for logging purposes
            context = self.get_context(ctxid)
            
            # Log the WebLLM message request
            PrintStyle(
                background_color="#2E86AB", font_color="white", bold=True, padding=True
            ).print(f"WebLLM message request:")
            PrintStyle(font_color="white", padding=False).print(f"> Model: {model_name}")
            PrintStyle(font_color="white", padding=False).print(f"> Message: {text}")
            
            # Log to context
            context.log.log(
                type="webllm_request",
                heading="WebLLM message request",
                content=text,
                kvps={
                    "model": model_name,
                    "system": system_prompt,
                    "provider": "WebLLM"
                },
            )
            
            # Return response indicating WebLLM should handle this
            # The frontend will intercept this response and process it with WebLLM
            return {
                "webllm_request": True,
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt} if system_prompt else None,
                    {"role": "user", "content": text}
                ],
                "context": context.id,
                "message": "Processing with WebLLM..."
            }
            
        except Exception as e:
            PrintStyle.error(f"WebLLM API error: {str(e)}")
            return {"error": f"WebLLM processing failed: {str(e)}"}
    
    async def log_webllm_response(self, input: dict, request: Request) -> dict | Response:
        """
        Log WebLLM response from the frontend
        """
        try:
            ctxid = input.get("context", "")
            response_text = input.get("response", "")
            model_name = input.get("model", "")
            usage = input.get("usage", {})
            
            context = self.get_context(ctxid)
            
            # Log the response
            PrintStyle(
                background_color="#28A745", font_color="white", bold=True, padding=True
            ).print(f"WebLLM response:")
            PrintStyle(font_color="white", padding=False).print(f"> Model: {model_name}")
            PrintStyle(font_color="white", padding=False).print(f"> Response: {response_text[:100]}...")
            
            context.log.log(
                type="webllm_response",
                heading="WebLLM response",
                content=response_text,
                kvps={
                    "model": model_name,
                    "provider": "WebLLM",
                    "usage": usage
                },
            )
            
            return {"logged": True, "context": context.id}
            
        except Exception as e:
            PrintStyle.error(f"WebLLM response logging error: {str(e)}")
            return {"error": f"Failed to log WebLLM response: {str(e)}"}


class WebllmMessageLog(ApiHandler):
    """
    API handler for logging WebLLM responses
    """
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        webllm_handler = WebllmMessage(self.app, self.thread_lock)
        return await webllm_handler.log_webllm_response(input, request)