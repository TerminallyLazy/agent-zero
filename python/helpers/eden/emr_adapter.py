"""
Eden Clinical Inboxologist - EMR Adapter Interface

Abstract interface for EMR integrations, allowing Eden to work with
multiple EMR systems (Dr. Chrono, Epic, Cerner, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
from enum import Enum

from .models import Patient, TaskCategory


class InboxItemType(Enum):
    """Type of inbox item from EMR."""
    LAB_RESULT = "lab_result"
    PATIENT_MESSAGE = "patient_message"
    REFILL_REQUEST = "refill_request"
    REFERRAL = "referral"
    PRIOR_AUTH = "prior_auth"
    APPOINTMENT_REQUEST = "appointment_request"
    BILLING_INQUIRY = "billing_inquiry"
    INTERNAL_MESSAGE = "internal_message"


@dataclass
class InboxItem:
    """Normalized inbox item from any EMR."""
    id: str
    emr_id: str  # Original ID in EMR system
    type: InboxItemType
    patient_id: str
    patient_name: str

    title: str
    content: str
    received_at: datetime

    # Original raw data from EMR
    raw_data: dict

    # Type-specific fields
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_task_category(self) -> TaskCategory:
        """Convert inbox item type to Eden task category."""
        mapping = {
            InboxItemType.LAB_RESULT: TaskCategory.LAB,
            InboxItemType.PATIENT_MESSAGE: TaskCategory.MESSAGE,
            InboxItemType.REFILL_REQUEST: TaskCategory.REFILL,
            InboxItemType.REFERRAL: TaskCategory.REFERRAL,
            InboxItemType.PRIOR_AUTH: TaskCategory.PRIOR_AUTH,
            InboxItemType.APPOINTMENT_REQUEST: TaskCategory.SCHEDULING,
            InboxItemType.BILLING_INQUIRY: TaskCategory.BILLING,
            InboxItemType.INTERNAL_MESSAGE: TaskCategory.INTERNAL,
        }
        return mapping.get(self.type, TaskCategory.MESSAGE)


@dataclass
class Message:
    """A message to send to a patient."""
    subject: str
    body: str
    patient_id: str


@dataclass
class ChartUpdate:
    """An update to a patient's chart."""
    patient_id: str
    note_type: str
    content: str
    metadata: dict = None


class EMRAdapter(ABC):
    """
    Abstract base class for EMR integrations.

    Implement this interface to add support for a new EMR system.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the EMR system."""
        pass

    @abstractmethod
    async def connect(self, credentials: dict) -> bool:
        """
        Establish connection to EMR.

        Args:
            credentials: EMR-specific credentials (tokens, API keys, etc.)

        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to EMR."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if connection is active and valid."""
        pass

    # ─────────────────────────────────────────────────────────────────
    # Inbox Operations
    # ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def fetch_inbox_items(
        self,
        since: Optional[datetime] = None,
        types: Optional[list[InboxItemType]] = None,
    ) -> list[InboxItem]:
        """
        Fetch inbox items from EMR.

        Args:
            since: Only fetch items after this datetime
            types: Filter to specific item types

        Returns:
            List of normalized inbox items
        """
        pass

    @abstractmethod
    async def mark_item_processed(self, item_id: str) -> bool:
        """
        Mark an inbox item as processed in the EMR.

        Args:
            item_id: The EMR item ID

        Returns:
            True if successful
        """
        pass

    # ─────────────────────────────────────────────────────────────────
    # Patient Operations
    # ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_patient(self, patient_id: str) -> Patient:
        """
        Fetch patient demographics.

        Args:
            patient_id: The EMR patient ID

        Returns:
            Patient object
        """
        pass

    @abstractmethod
    async def get_patient_chart_summary(self, patient_id: str) -> dict:
        """
        Fetch patient chart summary including conditions, meds, allergies.

        Args:
            patient_id: The EMR patient ID

        Returns:
            Dict with chart summary data
        """
        pass

    @abstractmethod
    async def get_patient_visit_history(
        self,
        patient_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Fetch patient's recent visits.

        Args:
            patient_id: The EMR patient ID
            limit: Maximum number of visits to return

        Returns:
            List of visit records
        """
        pass

    # ─────────────────────────────────────────────────────────────────
    # Messaging
    # ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def send_message(self, message: Message) -> bool:
        """
        Send a message to a patient.

        Args:
            message: The message to send

        Returns:
            True if successful
        """
        pass

    # ─────────────────────────────────────────────────────────────────
    # Medications
    # ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def approve_refill(
        self,
        medication_id: str,
        quantity: int,
        refills: int,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Approve a medication refill request.

        Args:
            medication_id: The medication ID in EMR
            quantity: Quantity to dispense
            refills: Number of refills
            notes: Optional notes

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def deny_refill(
        self,
        medication_id: str,
        reason: str,
    ) -> bool:
        """
        Deny a medication refill request.

        Args:
            medication_id: The medication ID in EMR
            reason: Reason for denial

        Returns:
            True if successful
        """
        pass

    # ─────────────────────────────────────────────────────────────────
    # Chart Updates
    # ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def update_chart(self, update: ChartUpdate) -> bool:
        """
        Add a note or update to patient's chart.

        Args:
            update: The chart update

        Returns:
            True if successful
        """
        pass


# ─────────────────────────────────────────────────────────────────────────
# Dr. Chrono Adapter Implementation
# ─────────────────────────────────────────────────────────────────────────

from .drchrono_client import DrChronoClient, DrChronoCredentials


class DrChronoAdapter(EMRAdapter):
    """
    Dr. Chrono implementation of EMR adapter.
    """

    def __init__(self):
        self.client: Optional[DrChronoClient] = None
        self._credentials: Optional[DrChronoCredentials] = None

    @property
    def name(self) -> str:
        return "Dr. Chrono"

    async def connect(self, credentials: dict) -> bool:
        """Connect using OAuth credentials."""
        try:
            self._credentials = DrChronoCredentials(
                access_token=credentials["access_token"],
                refresh_token=credentials["refresh_token"],
                expires_at=datetime.fromisoformat(credentials.get("expires_at", datetime.now().isoformat())),
                client_id=credentials["client_id"],
                client_secret=credentials["client_secret"],
            )
            self.client = DrChronoClient(self._credentials)

            # Verify connection by fetching current user
            await self.client.get_current_user()
            return True

        except Exception as e:
            self.client = None
            return False

    async def disconnect(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None

    async def is_connected(self) -> bool:
        if not self.client:
            return False
        try:
            await self.client.get_current_user()
            return True
        except:
            return False

    # ─────────────────────────────────────────────────────────────────
    # Inbox Operations
    # ─────────────────────────────────────────────────────────────────

    async def fetch_inbox_items(
        self,
        since: Optional[datetime] = None,
        types: Optional[list[InboxItemType]] = None,
    ) -> list[InboxItem]:
        """Aggregate inbox items from all Dr. Chrono sources."""
        if not self.client:
            raise Exception("Not connected to Dr. Chrono")

        items = []

        # Fetch lab results
        if types is None or InboxItemType.LAB_RESULT in types:
            labs = await self.client.get_lab_results(since=since)
            for lab in labs:
                items.append(self._lab_to_inbox_item(lab))

        # Fetch patient messages
        if types is None or InboxItemType.PATIENT_MESSAGE in types:
            messages = await self.client.get_patient_messages(unread_only=True)
            for msg in messages:
                items.append(self._message_to_inbox_item(msg))

        # Fetch refill requests
        if types is None or InboxItemType.REFILL_REQUEST in types:
            refills = await self.client.get_refill_requests()
            for refill in refills:
                items.append(self._refill_to_inbox_item(refill))

        # Fetch referrals
        if types is None or InboxItemType.REFERRAL in types:
            referrals = await self.client.get_referrals(status="pending")
            for ref in referrals:
                items.append(self._referral_to_inbox_item(ref))

        return items

    def _lab_to_inbox_item(self, lab: dict) -> InboxItem:
        """Convert Dr. Chrono lab result to InboxItem."""
        return InboxItem(
            id=f"lab-{lab.get('id')}",
            emr_id=str(lab.get("id")),
            type=InboxItemType.LAB_RESULT,
            patient_id=str(lab.get("patient")),
            patient_name=lab.get("patient_name", "Unknown"),
            title=lab.get("name", "Lab Result"),
            content=str(lab.get("results", "")),
            received_at=datetime.fromisoformat(
                lab.get("received_date", datetime.now().isoformat())
            ),
            raw_data=lab,
            metadata={
                "test_name": lab.get("name"),
                "results": lab.get("results"),
                "reference_range": lab.get("reference_range"),
                "abnormal": lab.get("abnormal", False),
            },
        )

    def _message_to_inbox_item(self, msg: dict) -> InboxItem:
        """Convert Dr. Chrono patient message to InboxItem."""
        return InboxItem(
            id=f"msg-{msg.get('id')}",
            emr_id=str(msg.get("id")),
            type=InboxItemType.PATIENT_MESSAGE,
            patient_id=str(msg.get("patient")),
            patient_name=msg.get("patient_name", "Unknown"),
            title=msg.get("subject", "Patient Message"),
            content=msg.get("body", ""),
            received_at=datetime.fromisoformat(
                msg.get("created_at", datetime.now().isoformat())
            ),
            raw_data=msg,
        )

    def _refill_to_inbox_item(self, refill: dict) -> InboxItem:
        """Convert Dr. Chrono refill request to InboxItem."""
        med_name = refill.get("name", "Medication")
        return InboxItem(
            id=f"refill-{refill.get('id')}",
            emr_id=str(refill.get("id")),
            type=InboxItemType.REFILL_REQUEST,
            patient_id=str(refill.get("patient")),
            patient_name=refill.get("patient_name", "Unknown"),
            title=f"Refill Request: {med_name}",
            content=f"Patient requesting refill of {med_name}",
            received_at=datetime.fromisoformat(
                refill.get("refill_requested_date", datetime.now().isoformat())
            ),
            raw_data=refill,
            metadata={
                "medication_name": med_name,
                "dosage": refill.get("dosage"),
                "quantity": refill.get("quantity"),
                "refills_remaining": refill.get("refills"),
            },
        )

    def _referral_to_inbox_item(self, ref: dict) -> InboxItem:
        """Convert Dr. Chrono referral to InboxItem."""
        return InboxItem(
            id=f"ref-{ref.get('id')}",
            emr_id=str(ref.get("id")),
            type=InboxItemType.REFERRAL,
            patient_id=str(ref.get("patient")),
            patient_name=ref.get("patient_name", "Unknown"),
            title=f"Referral: {ref.get('specialist_name', 'Specialist')}",
            content=ref.get("reason", ""),
            received_at=datetime.fromisoformat(
                ref.get("created_at", datetime.now().isoformat())
            ),
            raw_data=ref,
        )

    async def mark_item_processed(self, item_id: str) -> bool:
        """Mark item as processed in Dr. Chrono."""
        if not self.client:
            raise Exception("Not connected to Dr. Chrono")

        # Parse item type from ID prefix
        if item_id.startswith("lab-"):
            emr_id = item_id[4:]
            await self.client.update_lab_result(emr_id, reviewed=True)
            return True
        elif item_id.startswith("msg-"):
            emr_id = item_id[4:]
            await self.client.mark_message_read(emr_id)
            return True

        return False

    # ─────────────────────────────────────────────────────────────────
    # Patient Operations
    # ─────────────────────────────────────────────────────────────────

    async def get_patient(self, patient_id: str) -> Patient:
        """Fetch patient from Dr. Chrono."""
        if not self.client:
            raise Exception("Not connected to Dr. Chrono")

        data = await self.client.get_patient(patient_id)

        return Patient(
            id=str(data.get("id")),
            name=f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
            dob=data.get("date_of_birth", ""),
            mrn=data.get("chart_id"),
            email=data.get("email"),
            phone=data.get("cell_phone") or data.get("home_phone"),
        )

    async def get_patient_chart_summary(self, patient_id: str) -> dict:
        """Fetch patient chart summary."""
        if not self.client:
            raise Exception("Not connected to Dr. Chrono")

        return await self.client.get_patient_chart(patient_id)

    async def get_patient_visit_history(
        self,
        patient_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Fetch patient visits."""
        if not self.client:
            raise Exception("Not connected to Dr. Chrono")

        appointments = await self.client.get_appointments(patient_id=patient_id)
        # Sort by date descending and limit
        sorted_appts = sorted(
            appointments,
            key=lambda x: x.get("scheduled_time", ""),
            reverse=True,
        )
        return sorted_appts[:limit]

    # ─────────────────────────────────────────────────────────────────
    # Messaging
    # ─────────────────────────────────────────────────────────────────

    async def send_message(self, message: Message) -> bool:
        """Send message via Dr. Chrono."""
        if not self.client:
            raise Exception("Not connected to Dr. Chrono")

        await self.client.send_patient_message(
            patient_id=message.patient_id,
            subject=message.subject,
            body=message.body,
        )
        return True

    # ─────────────────────────────────────────────────────────────────
    # Medications
    # ─────────────────────────────────────────────────────────────────

    async def approve_refill(
        self,
        medication_id: str,
        quantity: int,
        refills: int,
        notes: Optional[str] = None,
    ) -> bool:
        """Approve refill in Dr. Chrono."""
        if not self.client:
            raise Exception("Not connected to Dr. Chrono")

        await self.client.approve_refill(
            medication_id=medication_id,
            quantity=quantity,
            refills=refills,
            pharmacy_notes=notes,
        )
        return True

    async def deny_refill(
        self,
        medication_id: str,
        reason: str,
    ) -> bool:
        """Deny refill in Dr. Chrono."""
        if not self.client:
            raise Exception("Not connected to Dr. Chrono")

        await self.client.deny_refill(medication_id, reason)
        return True

    # ─────────────────────────────────────────────────────────────────
    # Chart Updates
    # ─────────────────────────────────────────────────────────────────

    async def update_chart(self, update: ChartUpdate) -> bool:
        """Update chart in Dr. Chrono."""
        # Dr. Chrono uses clinical notes for chart updates
        # This would need to be implemented based on their specific API
        # For now, return True as placeholder
        return True


# ─────────────────────────────────────────────────────────────────────────
# Adapter Registry
# ─────────────────────────────────────────────────────────────────────────

_adapters: dict[str, type[EMRAdapter]] = {
    "drchrono": DrChronoAdapter,
}


def get_adapter(emr_type: str) -> EMRAdapter:
    """
    Get an EMR adapter instance by type.

    Args:
        emr_type: The EMR type (e.g., "drchrono", "epic", "cerner")

    Returns:
        EMR adapter instance

    Raises:
        ValueError if EMR type not supported
    """
    adapter_class = _adapters.get(emr_type.lower())
    if not adapter_class:
        raise ValueError(f"Unsupported EMR type: {emr_type}")
    return adapter_class()


def register_adapter(emr_type: str, adapter_class: type[EMRAdapter]) -> None:
    """Register a new EMR adapter type."""
    _adapters[emr_type.lower()] = adapter_class


def list_adapters() -> list[str]:
    """List available EMR adapter types."""
    return list(_adapters.keys())
