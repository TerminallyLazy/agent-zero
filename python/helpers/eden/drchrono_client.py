"""
Eden Clinical Inboxologist - Dr. Chrono API Client

OAuth 2.0 integration with Dr. Chrono EHR API.
"""

import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class DrChronoCredentials:
    """OAuth credentials for Dr. Chrono."""
    access_token: str
    refresh_token: str
    expires_at: datetime
    client_id: str
    client_secret: str


class DrChronoClient:
    """
    Async client for Dr. Chrono EHR API.

    Handles:
    - OAuth token management with auto-refresh
    - Patient data retrieval
    - Lab results fetching
    - Patient messages
    - Medication/refill management
    - Referrals and prior authorizations
    """

    BASE_URL = "https://app.drchrono.com/api"
    AUTH_URL = "https://drchrono.com/o/authorize/"
    TOKEN_URL = "https://drchrono.com/o/token/"

    def __init__(self, credentials: DrChronoCredentials):
        self.credentials = credentials
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _refresh_tokens(self) -> bool:
        """Refresh OAuth tokens when expired."""
        try:
            session = await self._get_session()
            async with session.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.credentials.refresh_token,
                    "client_id": self.credentials.client_id,
                    "client_secret": self.credentials.client_secret,
                },
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Token refresh failed: {resp.status}")
                    return False

                data = await resp.json()
                self.credentials.access_token = data["access_token"]
                self.credentials.refresh_token = data.get(
                    "refresh_token", self.credentials.refresh_token
                )
                # Dr. Chrono tokens expire in 48 hours
                self.credentials.expires_at = datetime.now() + timedelta(
                    seconds=data.get("expires_in", 172800)
                )
                return True

        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        retry_on_401: bool = True,
    ) -> dict:
        """
        Make authenticated request to Dr. Chrono API.

        Handles automatic token refresh on 401.
        """
        # Check if token is about to expire
        if datetime.now() >= self.credentials.expires_at - timedelta(minutes=5):
            await self._refresh_tokens()

        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {self.credentials.access_token}",
            "Content-Type": "application/json",
        }

        url = f"{self.BASE_URL}{endpoint}"

        try:
            async with session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
            ) as resp:
                # Handle token expiration
                if resp.status == 401 and retry_on_401:
                    if await self._refresh_tokens():
                        return await self._request(
                            method, endpoint, params, json_data, retry_on_401=False
                        )
                    raise Exception("Authentication failed after token refresh")

                if resp.status >= 400:
                    text = await resp.text()
                    raise Exception(f"API error {resp.status}: {text}")

                return await resp.json()

        except aiohttp.ClientError as e:
            logger.error(f"Request error: {e}")
            raise

    # ─────────────────────────────────────────────────────────────────
    # Patient Operations
    # ─────────────────────────────────────────────────────────────────

    async def get_patients(
        self,
        search: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Fetch patients with optional search filter.

        Args:
            search: Optional name search string
            limit: Maximum results to return

        Returns:
            List of patient records
        """
        params = {"page_size": limit}
        if search:
            params["search"] = search

        data = await self._request("GET", "/patients", params=params)
        return data.get("results", [])

    async def get_patient(self, patient_id: str) -> dict:
        """Fetch single patient by ID."""
        return await self._request("GET", f"/patients/{patient_id}")

    async def get_patient_chart(self, patient_id: str) -> dict:
        """Fetch patient chart summary including conditions, meds, allergies."""
        # Aggregate from multiple endpoints
        chart = {"patient_id": patient_id}

        # Get conditions
        conditions = await self._request(
            "GET", "/clinical_notes", params={"patient": patient_id}
        )
        chart["conditions"] = conditions.get("results", [])

        # Get medications
        meds = await self._request(
            "GET", "/medications", params={"patient": patient_id}
        )
        chart["medications"] = meds.get("results", [])

        # Get allergies
        allergies = await self._request(
            "GET", "/allergies", params={"patient": patient_id}
        )
        chart["allergies"] = allergies.get("results", [])

        return chart

    # ─────────────────────────────────────────────────────────────────
    # Lab Results
    # ─────────────────────────────────────────────────────────────────

    async def get_lab_results(
        self,
        since: Optional[datetime] = None,
        patient_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch lab results.

        Args:
            since: Only fetch results after this datetime
            patient_id: Filter to specific patient

        Returns:
            List of lab result records
        """
        params = {}
        if since:
            params["since"] = since.isoformat()
        if patient_id:
            params["patient"] = patient_id

        data = await self._request("GET", "/lab_results", params=params)
        return data.get("results", [])

    async def get_lab_result(self, lab_id: str) -> dict:
        """Fetch single lab result by ID."""
        return await self._request("GET", f"/lab_results/{lab_id}")

    async def update_lab_result(
        self,
        lab_id: str,
        reviewed: bool = True,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Update lab result status.

        Args:
            lab_id: Lab result ID
            reviewed: Mark as reviewed
            notes: Optional notes to add
        """
        payload = {"reviewed": reviewed}
        if notes:
            payload["notes"] = notes

        return await self._request("PATCH", f"/lab_results/{lab_id}", json_data=payload)

    # ─────────────────────────────────────────────────────────────────
    # Patient Messages
    # ─────────────────────────────────────────────────────────────────

    async def get_patient_messages(
        self,
        unread_only: bool = True,
        patient_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch patient portal messages.

        Args:
            unread_only: Only fetch unread messages
            patient_id: Filter to specific patient
        """
        params = {}
        if unread_only:
            params["read"] = "false"
        if patient_id:
            params["patient"] = patient_id

        data = await self._request("GET", "/patient_messages", params=params)
        return data.get("results", [])

    async def send_patient_message(
        self,
        patient_id: str,
        subject: str,
        body: str,
    ) -> dict:
        """
        Send message to patient via portal.

        Args:
            patient_id: Recipient patient ID
            subject: Message subject
            body: Message body text
        """
        return await self._request(
            "POST",
            "/patient_messages",
            json_data={
                "patient": patient_id,
                "subject": subject,
                "body": body,
            },
        )

    async def mark_message_read(self, message_id: str) -> dict:
        """Mark a patient message as read."""
        return await self._request(
            "PATCH",
            f"/patient_messages/{message_id}",
            json_data={"read": True},
        )

    # ─────────────────────────────────────────────────────────────────
    # Medications & Refills
    # ─────────────────────────────────────────────────────────────────

    async def get_medications(
        self,
        patient_id: Optional[str] = None,
        refill_requested: bool = False,
    ) -> list[dict]:
        """
        Fetch medications.

        Args:
            patient_id: Filter to specific patient
            refill_requested: Only show pending refill requests
        """
        params = {}
        if patient_id:
            params["patient"] = patient_id
        if refill_requested:
            params["refill_requested"] = "true"

        data = await self._request("GET", "/medications", params=params)
        return data.get("results", [])

    async def get_refill_requests(self) -> list[dict]:
        """Fetch all pending refill requests."""
        return await self.get_medications(refill_requested=True)

    async def approve_refill(
        self,
        medication_id: str,
        quantity: int,
        refills: int,
        pharmacy_notes: Optional[str] = None,
    ) -> dict:
        """
        Approve a medication refill request.

        Args:
            medication_id: Medication ID
            quantity: Quantity to dispense
            refills: Number of refills to authorize
            pharmacy_notes: Optional notes for pharmacy
        """
        payload = {
            "quantity": quantity,
            "refills": refills,
            "refill_requested": False,  # Clear the request
        }
        if pharmacy_notes:
            payload["pharmacy_notes"] = pharmacy_notes

        return await self._request(
            "PATCH", f"/medications/{medication_id}", json_data=payload
        )

    async def deny_refill(
        self,
        medication_id: str,
        reason: str,
    ) -> dict:
        """
        Deny a medication refill request.

        Args:
            medication_id: Medication ID
            reason: Reason for denial
        """
        return await self._request(
            "PATCH",
            f"/medications/{medication_id}",
            json_data={
                "refill_requested": False,
                "notes": f"Refill denied: {reason}",
            },
        )

    # ─────────────────────────────────────────────────────────────────
    # Referrals
    # ─────────────────────────────────────────────────────────────────

    async def get_referrals(
        self,
        status: Optional[str] = None,
        patient_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch referrals.

        Args:
            status: Filter by status (pending, completed, etc.)
            patient_id: Filter to specific patient
        """
        params = {}
        if status:
            params["status"] = status
        if patient_id:
            params["patient"] = patient_id

        data = await self._request("GET", "/referrals", params=params)
        return data.get("results", [])

    async def create_referral(
        self,
        patient_id: str,
        specialist_id: str,
        reason: str,
        notes: Optional[str] = None,
    ) -> dict:
        """Create a new referral."""
        payload = {
            "patient": patient_id,
            "specialist": specialist_id,
            "reason": reason,
        }
        if notes:
            payload["notes"] = notes

        return await self._request("POST", "/referrals", json_data=payload)

    # ─────────────────────────────────────────────────────────────────
    # Appointments
    # ─────────────────────────────────────────────────────────────────

    async def get_appointments(
        self,
        patient_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[dict]:
        """Fetch appointments."""
        params = {}
        if patient_id:
            params["patient"] = patient_id
        if date_from:
            params["date_range"] = date_from.strftime("%Y-%m-%d")
        if date_to:
            params["date_range"] += f"/{date_to.strftime('%Y-%m-%d')}"

        data = await self._request("GET", "/appointments", params=params)
        return data.get("results", [])

    async def get_patient_last_visit(self, patient_id: str) -> Optional[dict]:
        """Get patient's most recent appointment."""
        appointments = await self.get_appointments(patient_id=patient_id)
        if appointments:
            # Sort by date descending
            sorted_appts = sorted(
                appointments,
                key=lambda x: x.get("scheduled_time", ""),
                reverse=True,
            )
            # Return most recent past appointment
            now = datetime.now().isoformat()
            for appt in sorted_appts:
                if appt.get("scheduled_time", "") < now:
                    return appt
        return None

    # ─────────────────────────────────────────────────────────────────
    # User/Provider Info
    # ─────────────────────────────────────────────────────────────────

    async def get_current_user(self) -> dict:
        """Get the currently authenticated user/provider."""
        return await self._request("GET", "/users/current")

    async def get_doctor(self, doctor_id: str) -> dict:
        """Get doctor details."""
        return await self._request("GET", f"/doctors/{doctor_id}")


# ─────────────────────────────────────────────────────────────────────────
# OAuth Flow Helpers
# ─────────────────────────────────────────────────────────────────────────


def get_authorization_url(
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
) -> str:
    """
    Generate OAuth authorization URL.

    Args:
        client_id: Dr. Chrono app client ID
        redirect_uri: Callback URL after authorization
        scopes: List of requested scopes

    Returns:
        Authorization URL to redirect user to
    """
    scope_str = " ".join(scopes)
    return (
        f"{DrChronoClient.AUTH_URL}"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope_str}"
    )


async def exchange_code_for_tokens(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> DrChronoCredentials:
    """
    Exchange authorization code for access tokens.

    Args:
        code: Authorization code from callback
        client_id: Dr. Chrono app client ID
        client_secret: Dr. Chrono app client secret
        redirect_uri: Callback URL (must match authorization request)

    Returns:
        DrChronoCredentials with access and refresh tokens
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            DrChronoClient.TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Token exchange failed: {text}")

            data = await resp.json()

            return DrChronoCredentials(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=datetime.now() + timedelta(seconds=data.get("expires_in", 172800)),
                client_id=client_id,
                client_secret=client_secret,
            )


# Default scopes for Eden
EDEN_SCOPES = [
    "patients:read",
    "patients:write",
    "labs:read",
    "labs:write",
    "clinical:read",
    "clinical:write",
    "messages:read",
    "messages:write",
    "billing:read",
    "calendar:read",
    "calendar:write",
]
