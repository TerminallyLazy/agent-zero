"""
Eden Tool - Message Drafter

Agent tool for drafting patient communication messages
that match the physician's communication style.
"""

from dataclasses import dataclass
from typing import Optional
import re

try:
    from python.helpers.tool import Tool, Response
except ImportError:
    @dataclass
    class Response:
        message: str
        break_loop: bool = False
        additional: dict = None

    class Tool:
        def __init__(self, agent, name, method, args, message, loop_data):
            self.agent = agent
            self.name = name
            self.method = method
            self.args = args


# Message templates by category and sentiment
TEMPLATES = {
    "lab_normal": {
        "warm": """Hi {patient_first_name},

Great news! Your recent {test_name} results are in and everything looks good. {specific_results}

Keep up the excellent work with your health habits. We'll check in again at your next scheduled appointment.

Best,
{physician_name}""",

        "professional": """Dear {patient_name},

Your recent laboratory results for {test_name} have been reviewed. All values are within normal limits. {specific_results}

No immediate action is required. Please continue with your current care plan.

Sincerely,
{physician_name}""",
    },

    "lab_abnormal": {
        "warm": """Hi {patient_first_name},

Your recent lab results are in. While most look good, I noticed {abnormal_summary}.

This doesn't necessarily mean there's a problem, but I'd like to discuss it with you. {action_needed}

Please don't hesitate to reach out with questions.

Best,
{physician_name}""",

        "professional": """Dear {patient_name},

Your recent laboratory results have been reviewed. The following values require attention: {abnormal_summary}.

{action_needed}

Please contact our office at your earliest convenience.

Sincerely,
{physician_name}""",
    },

    "refill_approved": {
        "warm": """Hi {patient_first_name},

Good news! Your refill request for {medication_name} has been approved and sent to {pharmacy_name}.

It should be ready for pickup soon. If you have any questions about your medication, let us know.

Best,
{physician_name}""",

        "professional": """Dear {patient_name},

Your medication refill request for {medication_name} has been approved. The prescription has been transmitted to {pharmacy_name}.

Please allow adequate time for processing before pickup.

Sincerely,
{physician_name}""",
    },

    "refill_denied": {
        "warm": """Hi {patient_first_name},

I received your refill request for {medication_name}. Before I can approve it, {denial_reason}.

Please schedule an appointment so we can review your current treatment plan together.

Best,
{physician_name}""",

        "professional": """Dear {patient_name},

Your refill request for {medication_name} requires further review. {denial_reason}

Please schedule a follow-up appointment at your earliest convenience.

Sincerely,
{physician_name}""",
    },

    "appointment_confirmation": {
        "warm": """Hi {patient_first_name},

Great! I've received your request to schedule {appointment_type}. Our scheduling team will reach out shortly with available times.

You can also book directly through the patient portal if you prefer.

See you soon!
{physician_name}""",

        "professional": """Dear {patient_name},

Your request for {appointment_type} has been received. Our scheduling coordinator will contact you to arrange a convenient time.

Alternatively, you may schedule through the patient portal.

Sincerely,
{physician_name}""",
    },

    "general_response": {
        "warm": """Hi {patient_first_name},

Thanks for reaching out. {response_body}

Let me know if you have any other questions.

Best,
{physician_name}""",

        "professional": """Dear {patient_name},

Thank you for your message. {response_body}

Please contact our office if you have additional questions.

Sincerely,
{physician_name}""",
    },
}


class MessageDrafterTool(Tool):
    """
    Draft patient communication messages.

    Methods:
    - draft: Create a message draft using templates
    - personalize: Adjust a draft to match physician style
    - classify: Classify incoming message for routing
    """

    # Learned physician style patterns (would be persisted)
    physician_style = {
        "greeting": "Hi",
        "closing": "Best",
        "uses_first_name": True,
        "tone": "warm",
        "signature": "Dr. Rothschild",
    }

    async def execute(self, **kwargs) -> Response:
        """Execute the message drafter tool."""
        method = self.method or "draft"

        if method == "draft":
            return await self._draft(kwargs)
        elif method == "personalize":
            return await self._personalize(kwargs)
        elif method == "classify":
            return await self._classify(kwargs)
        elif method == "learn_style":
            return await self._learn_style(kwargs)

        return Response(
            message=f"Unknown method: {method}",
            break_loop=False,
        )

    async def _draft(self, kwargs) -> Response:
        """
        Draft a message using templates.

        Args:
            category: Message category (lab_normal, refill_approved, etc.)
            patient_name: Full patient name
            patient_first_name: Patient's first name
            physician_name: Signing physician
            variables: Dict of template variables
        """
        category = kwargs.get("category", "general_response")
        patient_name = kwargs.get("patient_name", "")
        patient_first_name = kwargs.get("patient_first_name", "")
        physician_name = kwargs.get("physician_name", self.physician_style.get("signature", "Your care team"))
        variables = kwargs.get("variables", {})

        # Get tone from physician style
        tone = self.physician_style.get("tone", "warm")

        # Get template
        category_templates = TEMPLATES.get(category, TEMPLATES["general_response"])
        template = category_templates.get(tone, category_templates.get("warm", ""))

        if not template:
            return Response(
                message=f"No template found for category: {category}",
                break_loop=False,
            )

        # Build substitution dict
        subs = {
            "patient_name": patient_name,
            "patient_first_name": patient_first_name or patient_name.split()[0],
            "physician_name": physician_name,
            **variables,
        }

        # Substitute variables
        try:
            draft = template.format(**subs)
        except KeyError as e:
            # Handle missing variables gracefully
            draft = template
            for key, value in subs.items():
                draft = draft.replace("{" + key + "}", str(value))

        return Response(
            message="Draft created",
            break_loop=False,
            additional={
                "draft": draft,
                "category": category,
                "tone": tone,
            }
        )

    async def _personalize(self, kwargs) -> Response:
        """
        Personalize a draft to match physician style.

        Args:
            draft: The draft message to personalize
            examples: Optional list of example messages from physician
        """
        draft = kwargs.get("draft", "")
        examples = kwargs.get("examples", [])

        if not draft:
            return Response(
                message="No draft provided",
                break_loop=False,
            )

        # Apply physician style adjustments
        personalized = draft

        # Adjust greeting
        if self.physician_style.get("greeting"):
            personalized = re.sub(
                r'^(Hi|Hello|Dear)\s+',
                f"{self.physician_style['greeting']} ",
                personalized,
                count=1
            )

        # Adjust closing
        if self.physician_style.get("closing"):
            personalized = re.sub(
                r'(Best|Sincerely|Regards),\s*$',
                f"{self.physician_style['closing']},",
                personalized,
                flags=re.MULTILINE
            )

        return Response(
            message="Draft personalized",
            break_loop=False,
            additional={
                "draft": personalized,
                "style_applied": self.physician_style,
            }
        )

    async def _classify(self, kwargs) -> Response:
        """
        Classify an incoming patient message.

        Args:
            message: The patient's message text
            subject: Message subject line
        """
        message = kwargs.get("message", "").lower()
        subject = kwargs.get("subject", "").lower()
        combined = f"{subject} {message}"

        # Classification patterns
        classifications = {
            "refill_request": [
                "refill", "prescription", "medication", "need more",
                "running out", "ran out", "renew"
            ],
            "scheduling": [
                "schedule", "appointment", "visit", "see the doctor",
                "available", "book", "annual", "checkup", "physical"
            ],
            "billing": [
                "bill", "payment", "insurance", "charge", "cost",
                "copay", "statement", "invoice"
            ],
            "records": [
                "records", "documentation", "form", "paperwork",
                "letter", "copy of", "fax"
            ],
            "symptom_report": [
                "pain", "feeling", "symptoms", "sick", "hurts",
                "worse", "better", "concern", "worried"
            ],
            "medication_question": [
                "side effect", "how to take", "when to take",
                "can i take", "interaction", "dosage"
            ],
            "test_question": [
                "results", "test", "lab", "blood work", "imaging",
                "what does", "mean"
            ],
            "urgent": [
                "emergency", "urgent", "immediately", "severe",
                "chest pain", "breathing", "can't", "worst",
                "911", "er", "hospital"
            ],
        }

        # Score each classification
        scores = {}
        for category, keywords in classifications.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                scores[category] = score

        if not scores:
            classification = "general_inquiry"
            confidence = 0.5
        else:
            classification = max(scores, key=scores.get)
            confidence = min(0.95, 0.5 + (scores[classification] * 0.15))

        # Check for urgent keywords
        is_urgent = "urgent" in scores

        # Determine suggested action
        action_map = {
            "refill_request": "process_refill",
            "scheduling": "forward_to_scheduling",
            "billing": "forward_to_billing",
            "records": "forward_to_records",
            "symptom_report": "clinical_review",
            "medication_question": "draft_response",
            "test_question": "draft_response",
            "general_inquiry": "draft_response",
            "urgent": "escalate_immediately",
        }

        suggested_action = action_map.get(classification, "draft_response")
        if is_urgent:
            suggested_action = "escalate_immediately"
            confidence = 0.0  # Force escalation

        return Response(
            message=f"Message classified as: {classification}",
            break_loop=False,
            additional={
                "classification": classification,
                "confidence": confidence,
                "is_urgent": is_urgent,
                "suggested_action": suggested_action,
                "all_scores": scores,
            }
        )

    async def _learn_style(self, kwargs) -> Response:
        """
        Learn physician communication style from examples.

        Args:
            examples: List of example messages written by physician
        """
        examples = kwargs.get("examples", [])

        if not examples:
            return Response(
                message="No examples provided",
                break_loop=False,
            )

        # Analyze examples for patterns
        greetings = []
        closings = []
        uses_first_name = 0
        total = len(examples)

        for example in examples:
            # Extract greeting
            greeting_match = re.match(r'^(Hi|Hello|Dear|Hey)\s+', example)
            if greeting_match:
                greetings.append(greeting_match.group(1))

            # Extract closing
            closing_match = re.search(r'(Best|Sincerely|Regards|Thanks|Cheers),?\s*$', example, re.MULTILINE)
            if closing_match:
                closings.append(closing_match.group(1))

            # Check first name usage
            if re.search(r'^(Hi|Hello|Hey)\s+[A-Z][a-z]+,', example):
                uses_first_name += 1

        # Update style
        if greetings:
            self.physician_style["greeting"] = max(set(greetings), key=greetings.count)

        if closings:
            self.physician_style["closing"] = max(set(closings), key=closings.count)

        self.physician_style["uses_first_name"] = (uses_first_name / total) > 0.5

        # Determine overall tone
        warm_indicators = sum(1 for g in greetings if g in ["Hi", "Hey"])
        if warm_indicators > len(greetings) / 2:
            self.physician_style["tone"] = "warm"
        else:
            self.physician_style["tone"] = "professional"

        return Response(
            message=f"Learned style from {total} examples",
            break_loop=False,
            additional={
                "learned_style": self.physician_style,
                "examples_analyzed": total,
            }
        )


# Register as Agent Zero tool
MessageDrafter = MessageDrafterTool
