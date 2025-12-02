"""
Eden Tool - Lab Result Analyzer

Agent tool for analyzing lab results and generating patient communications.
"""

from dataclasses import dataclass
from typing import Optional
import re

try:
    from python.helpers.tool import Tool, Response
except ImportError:
    # Fallback for standalone testing
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


# Reference ranges for common lab tests
REFERENCE_RANGES = {
    # Lipid Panel
    "total_cholesterol": {"low": 0, "high": 200, "unit": "mg/dL", "critical_high": 300},
    "ldl": {"low": 0, "high": 100, "unit": "mg/dL", "critical_high": 190},
    "hdl": {"low": 40, "high": 999, "unit": "mg/dL"},  # Higher is better
    "triglycerides": {"low": 0, "high": 150, "unit": "mg/dL", "critical_high": 500},

    # Metabolic Panel
    "glucose": {"low": 70, "high": 100, "unit": "mg/dL", "critical_low": 50, "critical_high": 400},
    "a1c": {"low": 4.0, "high": 5.6, "unit": "%", "critical_high": 9.0},
    "creatinine": {"low": 0.7, "high": 1.3, "unit": "mg/dL"},
    "bun": {"low": 7, "high": 20, "unit": "mg/dL"},
    "sodium": {"low": 136, "high": 145, "unit": "mEq/L"},
    "potassium": {"low": 3.5, "high": 5.0, "unit": "mEq/L", "critical_low": 2.5, "critical_high": 6.5},

    # CBC
    "wbc": {"low": 4.5, "high": 11.0, "unit": "K/uL"},
    "rbc": {"low": 4.5, "high": 5.5, "unit": "M/uL"},
    "hemoglobin": {"low": 12.0, "high": 17.5, "unit": "g/dL"},
    "hematocrit": {"low": 36, "high": 50, "unit": "%"},
    "platelets": {"low": 150, "high": 400, "unit": "K/uL"},

    # Thyroid
    "tsh": {"low": 0.4, "high": 4.0, "unit": "mIU/L"},
    "t4": {"low": 0.8, "high": 1.8, "unit": "ng/dL"},

    # Liver
    "alt": {"low": 7, "high": 56, "unit": "U/L"},
    "ast": {"low": 10, "high": 40, "unit": "U/L"},
    "bilirubin": {"low": 0.1, "high": 1.2, "unit": "mg/dL"},
}


@dataclass
class LabValue:
    """A single lab test value."""
    name: str
    value: float
    unit: str
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    is_abnormal: bool = False
    is_critical: bool = False
    interpretation: str = "normal"


class LabAnalyzerTool(Tool):
    """
    Analyze lab results to determine if they're normal, abnormal, or critical.

    Methods:
    - analyze: Analyze a lab result set
    - generate_message: Generate patient-friendly message for results
    - compare_to_previous: Compare to previous results for trending
    """

    async def execute(self, **kwargs) -> Response:
        """Execute the lab analyzer tool."""
        method = self.method or "analyze"

        if method == "analyze":
            return await self._analyze(kwargs)
        elif method == "generate_message":
            return await self._generate_message(kwargs)
        elif method == "compare_to_previous":
            return await self._compare_to_previous(kwargs)

        return Response(
            message=f"Unknown method: {method}",
            break_loop=False,
        )

    async def _analyze(self, kwargs) -> Response:
        """
        Analyze lab results.

        Args:
            lab_data: Dict with test names and values
            patient_context: Optional dict with patient info

        Returns:
            Analysis with interpretation for each value
        """
        lab_data = kwargs.get("lab_data", {})
        patient_context = kwargs.get("patient_context", {})

        results = []
        has_abnormal = False
        has_critical = False

        for test_name, value in lab_data.items():
            # Normalize test name
            normalized = self._normalize_test_name(test_name)
            ref = REFERENCE_RANGES.get(normalized, {})

            lab_value = LabValue(
                name=test_name,
                value=float(value) if value else 0,
                unit=ref.get("unit", ""),
                reference_low=ref.get("low"),
                reference_high=ref.get("high"),
            )

            # Determine if abnormal
            if lab_value.reference_low and lab_value.value < lab_value.reference_low:
                lab_value.is_abnormal = True
                lab_value.interpretation = "low"
                if ref.get("critical_low") and lab_value.value < ref["critical_low"]:
                    lab_value.is_critical = True
                    has_critical = True
                else:
                    has_abnormal = True

            elif lab_value.reference_high and lab_value.value > lab_value.reference_high:
                lab_value.is_abnormal = True
                lab_value.interpretation = "high"
                if ref.get("critical_high") and lab_value.value > ref["critical_high"]:
                    lab_value.is_critical = True
                    has_critical = True
                else:
                    has_abnormal = True

            results.append({
                "name": lab_value.name,
                "value": lab_value.value,
                "unit": lab_value.unit,
                "interpretation": lab_value.interpretation,
                "is_abnormal": lab_value.is_abnormal,
                "is_critical": lab_value.is_critical,
                "reference_range": f"{lab_value.reference_low}-{lab_value.reference_high}" if lab_value.reference_low else "",
            })

        # Overall assessment
        if has_critical:
            overall = "CRITICAL - Immediate attention required"
            confidence_modifier = 0.0  # Always escalate
        elif has_abnormal:
            overall = "ABNORMAL - Review recommended"
            confidence_modifier = 0.6
        else:
            overall = "NORMAL - Routine results"
            confidence_modifier = 0.95

        return Response(
            message=f"Lab analysis complete: {overall}",
            break_loop=False,
            additional={
                "results": results,
                "overall": overall,
                "has_abnormal": has_abnormal,
                "has_critical": has_critical,
                "confidence_modifier": confidence_modifier,
            }
        )

    async def _generate_message(self, kwargs) -> Response:
        """
        Generate patient-friendly message for lab results.

        Args:
            analysis: Result from analyze method
            patient_name: Patient's first name
            physician_name: Signing physician name
            style: Message style (warm, professional)
        """
        analysis = kwargs.get("analysis", {})
        patient_name = kwargs.get("patient_name", "")
        physician_name = kwargs.get("physician_name", "Your care team")
        style = kwargs.get("style", "warm")

        results = analysis.get("results", [])
        overall = analysis.get("overall", "")

        # Determine message type
        if analysis.get("has_critical"):
            # Don't auto-generate for critical results
            return Response(
                message="Critical results should not be auto-messaged",
                break_loop=False,
                additional={"draft": None, "requires_physician": True}
            )

        if analysis.get("has_abnormal"):
            message = self._generate_abnormal_message(
                results, patient_name, physician_name, style
            )
        else:
            message = self._generate_normal_message(
                results, patient_name, physician_name, style
            )

        return Response(
            message="Draft message generated",
            break_loop=False,
            additional={"draft": message}
        )

    def _generate_normal_message(
        self,
        results: list,
        patient_name: str,
        physician_name: str,
        style: str,
    ) -> str:
        """Generate message for normal results."""
        greeting = f"Hi {patient_name}," if style == "warm" else f"Dear {patient_name},"

        # Group results by type
        test_names = [r["name"] for r in results]
        test_summary = ", ".join(test_names[:3])
        if len(test_names) > 3:
            test_summary += f" and {len(test_names) - 3} other tests"

        message = f"""{greeting}

Great news! Your recent lab results are in and everything looks good. Your {test_summary} are all within normal ranges.

Keep up the excellent work with your health habits. We'll check in again at your next scheduled appointment.

If you have any questions about these results, please don't hesitate to reach out.

Best regards,
{physician_name}"""

        return message

    def _generate_abnormal_message(
        self,
        results: list,
        patient_name: str,
        physician_name: str,
        style: str,
    ) -> str:
        """Generate message for abnormal (but not critical) results."""
        greeting = f"Hi {patient_name}," if style == "warm" else f"Dear {patient_name},"

        abnormal = [r for r in results if r["is_abnormal"]]
        normal = [r for r in results if not r["is_abnormal"]]

        abnormal_summary = ", ".join([
            f"{r['name']} ({r['interpretation']})"
            for r in abnormal
        ])

        message = f"""{greeting}

Your recent lab results are in. I wanted to review them with you.

Most of your results look good. However, a few values were outside the normal range:
- {abnormal_summary}

This doesn't necessarily mean there's a problem, but I'd like to discuss these results with you. Please schedule a follow-up appointment at your convenience, or reply to this message if you have immediate questions.

Best regards,
{physician_name}"""

        return message

    async def _compare_to_previous(self, kwargs) -> Response:
        """
        Compare current results to previous for trending.

        Args:
            current: Current lab results
            previous: Previous lab results
        """
        current = kwargs.get("current", {})
        previous = kwargs.get("previous", {})

        trends = []

        for test_name, current_value in current.items():
            if test_name in previous:
                prev_value = previous[test_name]
                try:
                    curr = float(current_value)
                    prev = float(prev_value)

                    if curr > prev * 1.1:
                        trend = "increasing"
                    elif curr < prev * 0.9:
                        trend = "decreasing"
                    else:
                        trend = "stable"

                    percent_change = ((curr - prev) / prev) * 100

                    trends.append({
                        "test": test_name,
                        "current": curr,
                        "previous": prev,
                        "trend": trend,
                        "percent_change": round(percent_change, 1),
                    })
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

        # Check for concerning trends
        concerning = [t for t in trends if abs(t["percent_change"]) > 20]

        return Response(
            message=f"Compared {len(trends)} tests to previous results",
            break_loop=False,
            additional={
                "trends": trends,
                "concerning_trends": concerning,
                "has_concerning": len(concerning) > 0,
            }
        )

    def _normalize_test_name(self, name: str) -> str:
        """Normalize test name for lookup."""
        normalized = name.lower().strip()

        # Common aliases
        aliases = {
            "hgb": "hemoglobin",
            "hct": "hematocrit",
            "plt": "platelets",
            "total chol": "total_cholesterol",
            "cholesterol": "total_cholesterol",
            "ldl-c": "ldl",
            "hdl-c": "hdl",
            "trig": "triglycerides",
            "fasting glucose": "glucose",
            "hba1c": "a1c",
            "hemoglobin a1c": "a1c",
            "glycated hemoglobin": "a1c",
            "creat": "creatinine",
            "na": "sodium",
            "k": "potassium",
        }

        return aliases.get(normalized, normalized.replace(" ", "_"))


# Register as Agent Zero tool
LabAnalyzer = LabAnalyzerTool
