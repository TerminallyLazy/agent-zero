"""
Eden Tool - Refill Request Evaluator

Agent tool for evaluating medication refill requests against
clinical criteria and policies.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

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


# Controlled substances that always require physician review
CONTROLLED_SUBSTANCES = {
    # Schedule II
    "oxycodone", "hydrocodone", "morphine", "fentanyl", "codeine",
    "methadone", "hydromorphone", "oxymorphone", "meperidine",
    "amphetamine", "methylphenidate", "lisdexamfetamine",
    "adderall", "ritalin", "concerta", "vyvanse",
    # Schedule III-IV
    "alprazolam", "xanax", "diazepam", "valium", "lorazepam", "ativan",
    "clonazepam", "klonopin", "temazepam", "triazolam",
    "zolpidem", "ambien", "eszopiclone", "lunesta",
    "tramadol", "carisoprodol",
    # Schedule V
    "pregabalin", "lyrica",
}

# Medications requiring monitoring
MONITORED_MEDICATIONS = {
    "warfarin": {"monitoring": "INR", "frequency_days": 30},
    "lithium": {"monitoring": "lithium level", "frequency_days": 90},
    "clozapine": {"monitoring": "ANC", "frequency_days": 7},
    "methotrexate": {"monitoring": "CBC, LFTs", "frequency_days": 90},
    "biologics": {"monitoring": "TB test", "frequency_days": 365},
}

# Standard refill quantities by medication type
STANDARD_QUANTITIES = {
    "maintenance": {"quantity": 90, "refills": 3},  # 90-day supply, 3 refills
    "acute": {"quantity": 30, "refills": 0},  # 30-day, no refills
    "controlled": {"quantity": 30, "refills": 0},  # 30-day, no refills (must renew)
}


@dataclass
class RefillDecision:
    """Result of refill evaluation."""
    approved: bool
    requires_review: bool
    reason: str
    confidence: float
    suggested_quantity: Optional[int] = None
    suggested_refills: Optional[int] = None
    warnings: list = None
    follow_up_needed: bool = False


class RefillEvaluatorTool(Tool):
    """
    Evaluate medication refill requests.

    Methods:
    - evaluate: Evaluate a refill request
    - check_early_refill: Check if refill is being requested early
    - check_interactions: Check for drug interactions
    """

    async def execute(self, **kwargs) -> Response:
        """Execute the refill evaluator tool."""
        method = self.method or "evaluate"

        if method == "evaluate":
            return await self._evaluate(kwargs)
        elif method == "check_early_refill":
            return await self._check_early_refill(kwargs)
        elif method == "check_interactions":
            return await self._check_interactions(kwargs)

        return Response(
            message=f"Unknown method: {method}",
            break_loop=False,
        )

    async def _evaluate(self, kwargs) -> Response:
        """
        Evaluate a medication refill request.

        Args:
            medication_name: Name of medication
            patient_context: Dict with patient info
                - last_visit_days: Days since last visit
                - has_active_prescription: Whether prescription is active
                - previous_refills: Number of refills already dispensed
                - conditions: Patient conditions
                - other_medications: Other active medications
            requested_quantity: Quantity requested
            last_fill_date: Date of last fill
        """
        medication_name = kwargs.get("medication_name", "").lower()
        patient_context = kwargs.get("patient_context", {})
        requested_quantity = kwargs.get("requested_quantity")
        last_fill_date = kwargs.get("last_fill_date")

        warnings = []
        decision = RefillDecision(
            approved=False,
            requires_review=True,
            reason="",
            confidence=0.5,
            warnings=[],
        )

        # Check 1: Is this a controlled substance?
        is_controlled = self._is_controlled(medication_name)
        if is_controlled:
            decision.requires_review = True
            decision.confidence = 0.0
            decision.reason = "Controlled substance - requires physician review"
            warnings.append("Controlled substance")
            return self._build_response(decision, warnings)

        # Check 2: Is there an active prescription?
        if not patient_context.get("has_active_prescription", True):
            decision.approved = False
            decision.requires_review = True
            decision.reason = "No active prescription on file"
            decision.confidence = 0.0
            return self._build_response(decision, warnings)

        # Check 3: When was last visit?
        last_visit_days = patient_context.get("last_visit_days", 999)
        if last_visit_days > 365:
            decision.approved = False
            decision.requires_review = True
            decision.reason = f"Patient has not been seen in {last_visit_days} days - visit required"
            decision.confidence = 0.3
            decision.follow_up_needed = True
            warnings.append("Overdue for visit")
            return self._build_response(decision, warnings)
        elif last_visit_days > 180:
            warnings.append(f"Last visit {last_visit_days} days ago")
            decision.confidence *= 0.8

        # Check 4: Is refill on schedule or early?
        if last_fill_date:
            try:
                last_fill = datetime.fromisoformat(last_fill_date)
                days_since_fill = (datetime.now() - last_fill).days
                expected_days = requested_quantity or 30

                if days_since_fill < expected_days * 0.7:
                    # Requesting more than 30% early
                    decision.requires_review = True
                    decision.reason = f"Early refill request - {days_since_fill} days since last fill"
                    decision.confidence = 0.4
                    warnings.append("Early refill")
            except:
                pass

        # Check 5: Does medication require monitoring?
        monitoring_req = self._requires_monitoring(medication_name)
        if monitoring_req:
            # Check if monitoring is current
            last_monitoring = patient_context.get("last_monitoring_days", 999)
            if last_monitoring > monitoring_req["frequency_days"]:
                decision.requires_review = True
                decision.reason = f"Required monitoring ({monitoring_req['monitoring']}) is overdue"
                decision.confidence = 0.3
                decision.follow_up_needed = True
                warnings.append(f"Monitoring overdue: {monitoring_req['monitoring']}")

        # Check 6: Any contraindications or interactions?
        conditions = patient_context.get("conditions", [])
        other_meds = patient_context.get("other_medications", [])

        # Simplified interaction check
        interactions = self._check_basic_interactions(medication_name, other_meds)
        if interactions:
            warnings.extend(interactions)
            decision.confidence *= 0.7

        # If we passed all checks with no major issues
        if not decision.reason and not warnings:
            decision.approved = True
            decision.requires_review = False
            decision.reason = "Routine refill - meets all criteria"
            decision.confidence = 0.92
            decision.suggested_quantity = requested_quantity or 90
            decision.suggested_refills = 3
        elif not decision.reason:
            # Minor warnings only
            decision.approved = True
            decision.requires_review = len(warnings) > 1
            decision.reason = "Approved with notes"
            decision.suggested_quantity = requested_quantity or 90
            decision.suggested_refills = 3

        return self._build_response(decision, warnings)

    def _build_response(self, decision: RefillDecision, warnings: list) -> Response:
        """Build response from decision."""
        decision.warnings = warnings

        return Response(
            message=f"Refill evaluation complete: {'Approved' if decision.approved else 'Review required'}",
            break_loop=False,
            additional={
                "approved": decision.approved,
                "requires_review": decision.requires_review,
                "reason": decision.reason,
                "confidence": decision.confidence,
                "suggested_quantity": decision.suggested_quantity,
                "suggested_refills": decision.suggested_refills,
                "warnings": warnings,
                "follow_up_needed": decision.follow_up_needed,
            }
        )

    def _is_controlled(self, medication_name: str) -> bool:
        """Check if medication is a controlled substance."""
        med_lower = medication_name.lower()
        return any(cs in med_lower for cs in CONTROLLED_SUBSTANCES)

    def _requires_monitoring(self, medication_name: str) -> Optional[dict]:
        """Check if medication requires monitoring."""
        med_lower = medication_name.lower()
        for med, req in MONITORED_MEDICATIONS.items():
            if med in med_lower:
                return req
        return None

    def _check_basic_interactions(
        self,
        medication: str,
        other_medications: list,
    ) -> list[str]:
        """Check for basic drug interactions."""
        interactions = []
        med_lower = medication.lower()
        other_lower = [m.lower() for m in other_medications]

        # Some basic interaction pairs
        interaction_pairs = [
            ("warfarin", "aspirin", "Increased bleeding risk"),
            ("warfarin", "nsaid", "Increased bleeding risk"),
            ("ace", "potassium", "Hyperkalemia risk"),
            ("ssri", "maoi", "Serotonin syndrome risk"),
            ("statin", "fibrate", "Myopathy risk"),
            ("metformin", "contrast", "Lactic acidosis risk"),
        ]

        for med1, med2, warning in interaction_pairs:
            if med1 in med_lower:
                if any(med2 in other for other in other_lower):
                    interactions.append(warning)
            elif med2 in med_lower:
                if any(med1 in other for other in other_lower):
                    interactions.append(warning)

        return interactions

    async def _check_early_refill(self, kwargs) -> Response:
        """
        Check if a refill is being requested early.

        Args:
            last_fill_date: Date of last fill
            quantity_dispensed: Quantity dispensed last time
            daily_dose: Daily dose frequency
        """
        last_fill_date = kwargs.get("last_fill_date")
        quantity_dispensed = kwargs.get("quantity_dispensed", 30)
        daily_dose = kwargs.get("daily_dose", 1)

        if not last_fill_date:
            return Response(
                message="Cannot determine - no last fill date",
                break_loop=False,
                additional={"is_early": None}
            )

        try:
            last_fill = datetime.fromisoformat(last_fill_date)
            days_supply = quantity_dispensed / daily_dose
            expected_refill_date = last_fill + timedelta(days=days_supply)
            days_until_expected = (expected_refill_date - datetime.now()).days

            is_early = days_until_expected > 7  # More than a week early

            return Response(
                message=f"Refill analysis complete - {'Early' if is_early else 'On schedule'}",
                break_loop=False,
                additional={
                    "is_early": is_early,
                    "days_until_expected": days_until_expected,
                    "expected_refill_date": expected_refill_date.isoformat(),
                    "days_supply": days_supply,
                }
            )

        except Exception as e:
            return Response(
                message=f"Error calculating refill timing: {str(e)}",
                break_loop=False,
                additional={"is_early": None, "error": str(e)}
            )

    async def _check_interactions(self, kwargs) -> Response:
        """
        Check for drug interactions.

        Args:
            medication: Primary medication
            other_medications: List of other medications
        """
        medication = kwargs.get("medication", "")
        other_medications = kwargs.get("other_medications", [])

        interactions = self._check_basic_interactions(medication, other_medications)

        severity = "none"
        if interactions:
            severity = "moderate"
            if any("risk" in i.lower() for i in interactions):
                severity = "significant"

        return Response(
            message=f"Interaction check complete - {len(interactions)} potential interactions",
            break_loop=False,
            additional={
                "interactions": interactions,
                "count": len(interactions),
                "severity": severity,
            }
        )


# Register as Agent Zero tool
RefillEvaluator = RefillEvaluatorTool
