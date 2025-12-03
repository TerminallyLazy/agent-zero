"""
Eden API - Chat Endpoint

POST /eden/chat - Context-aware chat with Eden AI assistant
"""

import json
from datetime import datetime
from typing import Optional

from litellm import acompletion

try:
    from python.helpers.api import ApiHandler
    from python.helpers import settings
except ImportError:
    class ApiHandler:
        @classmethod
        def requires_auth(cls) -> bool:
            return True

from python.helpers.eden.models import TaskStatus, TaskCategory
from python.helpers.eden.clustering import ClusteringService


# System prompt for Eden assistant
EDEN_SYSTEM_PROMPT = """You are Eden, an AI clinical inbox assistant for physicians. You help manage and triage their EMR inbox items including lab results, patient messages, refill requests, referrals, and more.

Your role is to:
1. Provide summaries and insights about the inbox state
2. Answer questions about specific patients or tasks
3. Explain your confidence scores and reasoning
4. Help prioritize what needs attention
5. Suggest actions based on clinical context

You have access to the current inbox context provided below. Use this information to give accurate, helpful responses.

Guidelines:
- Be concise and clinical in your responses
- Use the actual data from the context - don't make up patient names or details
- When discussing confidence scores, explain what factors contributed
- If asked about something not in the context, say so clearly
- Never provide medical advice - you assist with inbox management, not clinical decisions
- Refer to yourself as "Eden" and maintain a professional, supportive tone

Current Date: {current_date}
"""


class ChatHandler(ApiHandler):
    """Handle chat requests with context-aware AI responses."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request) -> dict:
        """Process a chat message and return AI response."""
        message = input.get("message", "").strip()
        if not message:
            return {"error": "Message is required", "success": False}

        # Get user-provided context (from frontend)
        user_context = input.get("context", {})

        # Get conversation history
        history = input.get("history", [])

        # Build full context from backend data
        full_context = await self._build_context(user_context)

        # Get AI response
        try:
            response = await self._get_ai_response(message, full_context, history)
            return {
                "success": True,
                "message": response,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"I apologize, but I encountered an error processing your request. Please try again."
            }

    async def _build_context(self, user_context: dict) -> str:
        """Build comprehensive context string from inbox state."""
        service = ClusteringService.get_instance()
        clusters = await service.get_clusters()
        stats = service.get_stats()

        # Build context sections
        context_parts = []

        # Stats overview
        context_parts.append(f"""## Inbox Overview
- Total tasks: {stats['total_tasks']}
- Auto-handled: {stats['auto_handled']}
- Pending review: {stats['pending'] + stats['needs_review']}
- Escalated: {stats['escalated']}
- Completed: {stats['completed']}
""")

        # Clusters summary
        if clusters:
            context_parts.append("## Patient Clusters")
            for cluster in clusters[:10]:  # Limit to 10 clusters
                task_summary = ", ".join([
                    f"{t.category.value}({t.status.value}, {int(t.confidence*100)}%)"
                    for t in cluster.tasks[:5]
                ])
                context_parts.append(f"""
### {cluster.patient.name} (ID: {cluster.patient.id})
- Tasks: {len(cluster.tasks)}
- Average Confidence: {int(cluster.avg_confidence * 100)}%
- Priority: {self._priority_label(cluster.priority)}
- Items: {task_summary}
""")

        # Escalated tasks (high priority)
        escalated = [
            t for c in clusters for t in c.tasks
            if t.status == TaskStatus.ESCALATED
        ]
        if escalated:
            context_parts.append("\n## Escalated Tasks (Require Immediate Attention)")
            for task in escalated[:5]:
                context_parts.append(f"""
- **{task.title}** for {task.patient.name}
  - Category: {task.category.value}
  - Confidence: {int(task.confidence * 100)}%
  - Summary: {task.summary}
  - Reasoning: {'; '.join(task.reasoning[:3]) if task.reasoning else 'N/A'}
""")

        # Pending review tasks
        pending = [
            t for c in clusters for t in c.tasks
            if t.status in [TaskStatus.PENDING, TaskStatus.NEEDS_REVIEW]
        ]
        if pending:
            context_parts.append("\n## Tasks Pending Review")
            for task in pending[:10]:
                draft_info = f"\n  - Draft: {task.draft_content[:100]}..." if task.draft_content else ""
                context_parts.append(f"""
- **{task.title}** for {task.patient.name}
  - Category: {task.category.value}
  - Confidence: {int(task.confidence * 100)}%
  - Summary: {task.summary}{draft_info}
""")

        # Recently auto-handled
        auto_handled = [
            t for c in clusters for t in c.tasks
            if t.status == TaskStatus.AUTO_HANDLED
        ][:5]
        if auto_handled:
            context_parts.append("\n## Recently Auto-Handled")
            for task in auto_handled:
                context_parts.append(f"- {task.title} for {task.patient.name} ({task.category.value})")

        # Category breakdown
        category_counts = {}
        for cluster in clusters:
            for task in cluster.tasks:
                cat = task.category.value
                category_counts[cat] = category_counts.get(cat, 0) + 1

        if category_counts:
            context_parts.append("\n## Tasks by Category")
            for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
                context_parts.append(f"- {cat}: {count}")

        # Selected cluster detail (if any)
        if user_context.get("selectedCluster"):
            sc = user_context["selectedCluster"]
            context_parts.append(f"\n## Currently Selected: {sc.get('patient', {}).get('name', 'Unknown')}")

        return "\n".join(context_parts)

    def _priority_label(self, priority: int) -> str:
        """Convert priority number to label."""
        labels = {
            0: "Critical (Escalated)",
            1: "High (Needs Review)",
            2: "Medium (Pending)",
            3: "Low (Auto-handled)"
        }
        return labels.get(priority, f"Priority {priority}")

    async def _get_ai_response(self, message: str, context: str, history: list) -> str:
        """Get response from LLM."""
        # Get model settings
        app_settings = settings.get_settings()

        # Build messages
        messages = [
            {
                "role": "system",
                "content": EDEN_SYSTEM_PROMPT.format(
                    current_date=datetime.now().strftime("%Y-%m-%d %H:%M")
                ) + f"\n\n# Current Inbox Context\n{context}"
            }
        ]

        # Add conversation history (limit to last 10 messages)
        for msg in history[-10:]:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

        # Add current message
        messages.append({
            "role": "user",
            "content": message
        })

        # Build model identifier
        provider = app_settings.get("chat_model_provider", "openrouter")
        model_name = app_settings.get("chat_model_name", "anthropic/claude-3.5-sonnet")

        # Format model string for litellm
        if provider == "anthropic":
            model = model_name
        elif provider == "openrouter":
            model = f"openrouter/{model_name}"
        elif provider == "openai":
            model = model_name
        else:
            model = f"{provider}/{model_name}"

        # Get additional kwargs
        model_kwargs = app_settings.get("chat_model_kwargs", {})
        api_base = app_settings.get("chat_model_api_base", "")

        # Make the API call
        call_kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7,
        }

        if api_base:
            call_kwargs["api_base"] = api_base

        if model_kwargs:
            call_kwargs.update(model_kwargs)

        response = await acompletion(**call_kwargs)

        # Extract response text
        if hasattr(response, 'choices') and response.choices:
            return response.choices[0].message.content

        return "I apologize, but I couldn't generate a response. Please try again."


# Handler for /eden/chat endpoint
Chat = ChatHandler
