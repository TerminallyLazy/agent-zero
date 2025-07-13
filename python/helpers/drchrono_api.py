"""
DrChrono API Helper Module

Provides core functionality for DrChrono API operations including:
- OAuth2 authentication and token management
- Rate limiting and retry logic  
- Error handling and categorization
- Request/response utilities
- HIPAA-compliant logging
"""

import requests
import json
import time
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from python.helpers.errors import handle_error
import asyncio
import aiohttp


@dataclass
class DrChronoConfig:
    """Configuration for DrChrono API client"""
    client_id: str
    client_secret: str
    redirect_uri: str
    base_url: str = "https://drchrono.com"
    rate_limit_per_hour: int = 500
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class TokenInfo:
    """OAuth2 token information"""
    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: str = "Bearer"
    scope: str = ""
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired with 5 minute buffer"""
        return datetime.now() >= (self.expires_at - timedelta(minutes=5))
    
    @property
    def authorization_header(self) -> str:
        """Get Authorization header value"""
        return f"{self.token_type} {self.access_token}"


class RateLimiter:
    """Rate limiter for DrChrono API requests"""
    
    def __init__(self, max_requests_per_hour: int = 500):
        self.max_requests = max_requests_per_hour
        self.requests_made = []
        self.lock = asyncio.Lock()
    
    async def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        async with self.lock:
            now = datetime.now()
            # Remove requests older than 1 hour
            self.requests_made = [req_time for req_time in self.requests_made 
                                if now - req_time < timedelta(hours=1)]
            
            if len(self.requests_made) >= self.max_requests:
                # Wait until oldest request is more than 1 hour old
                oldest_request = min(self.requests_made)
                wait_time = (oldest_request + timedelta(hours=1) - now).total_seconds()
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    return await self.wait_if_needed()
            
            self.requests_made.append(now)


class DrChronoAPIError(Exception):
    """Base exception for DrChrono API errors"""
    
    def __init__(self, message: str, status_code: Optional[int] = None, 
                 response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class DrChronoAuthError(DrChronoAPIError):
    """Authentication related errors"""
    pass


class DrChronoRateLimitError(DrChronoAPIError):
    """Rate limit exceeded errors"""
    pass


class DrChronoClient:
    """Main DrChrono API client with HIPAA-compliant operations"""
    
    def __init__(self, config: DrChronoConfig):
        self.config = config
        self.token_info: Optional[TokenInfo] = None
        self.rate_limiter = RateLimiter(config.rate_limit_per_hour)
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
            headers={"User-Agent": "Agent-Zero-DrChrono-Client/1.0"}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    def set_token_info(self, token_info: TokenInfo):
        """Set token information for authenticated requests"""
        self.token_info = token_info
    
    async def refresh_token_if_needed(self) -> bool:
        """Refresh token if expired, returns True if refreshed"""
        if not self.token_info or not self.token_info.is_expired:
            return False
        
        refresh_data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.token_info.refresh_token,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret
        }
        
        try:
            async with self.session.post(
                f"{self.config.base_url}/o/token/",
                data=refresh_data
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    expires_at = datetime.now() + timedelta(seconds=token_data['expires_in'])
                    
                    self.token_info = TokenInfo(
                        access_token=token_data['access_token'],
                        refresh_token=token_data.get('refresh_token', self.token_info.refresh_token),
                        expires_at=expires_at,
                        token_type=token_data.get('token_type', 'Bearer'),
                        scope=token_data.get('scope', self.token_info.scope)
                    )
                    return True
                else:
                    error_data = await response.json() if response.content_type == 'application/json' else {}
                    raise DrChronoAuthError(
                        f"Token refresh failed: {response.status}",
                        status_code=response.status,
                        response_data=error_data
                    )
        except Exception as e:
            handle_error(e)
            raise DrChronoAuthError(f"Token refresh error: {str(e)}")
    
    async def make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """Make authenticated API request with retry logic"""
        
        if not self.token_info:
            raise DrChronoAuthError("No token available. Please authenticate first.")
        
        # Refresh token if needed
        await self.refresh_token_if_needed()
        
        # Wait for rate limiting
        await self.rate_limiter.wait_if_needed()
        
        # Prepare request
        url = f"{self.config.base_url}{endpoint}"
        request_headers = {
            "Authorization": self.token_info.authorization_header,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if headers:
            request_headers.update(headers)
        
        try:
            async with self.session.request(
                method=method.upper(),
                url=url,
                json=data if method.upper() in ['POST', 'PUT', 'PATCH'] else None,
                params=params,
                headers=request_headers
            ) as response:
                
                # Handle rate limiting
                if response.status == 429:
                    if retry_count < self.config.max_retries:
                        retry_delay = self.config.retry_delay * (2 ** retry_count)
                        await asyncio.sleep(retry_delay)
                        return await self.make_request(
                            method, endpoint, data, params, headers, retry_count + 1
                        )
                    else:
                        raise DrChronoRateLimitError(
                            "Rate limit exceeded and max retries reached",
                            status_code=429
                        )
                
                # Handle authentication errors
                if response.status == 401:
                    raise DrChronoAuthError(
                        "Authentication failed - token may be invalid",
                        status_code=401
                    )
                
                # Handle other client errors
                if 400 <= response.status < 500:
                    error_data = await response.json() if response.content_type == 'application/json' else {}
                    raise DrChronoAPIError(
                        f"Client error: {response.status}",
                        status_code=response.status,
                        response_data=error_data
                    )
                
                # Handle server errors with retry
                if response.status >= 500:
                    if retry_count < self.config.max_retries:
                        retry_delay = self.config.retry_delay * (2 ** retry_count)
                        await asyncio.sleep(retry_delay)
                        return await self.make_request(
                            method, endpoint, data, params, headers, retry_count + 1
                        )
                    else:
                        error_data = await response.json() if response.content_type == 'application/json' else {}
                        raise DrChronoAPIError(
                            f"Server error: {response.status}",
                            status_code=response.status,
                            response_data=error_data
                        )
                
                # Success - return JSON data
                if response.content_type == 'application/json':
                    return await response.json()
                else:
                    return {"raw_content": await response.text()}
                    
        except aiohttp.ClientError as e:
            if retry_count < self.config.max_retries:
                retry_delay = self.config.retry_delay * (2 ** retry_count)
                await asyncio.sleep(retry_delay)
                return await self.make_request(
                    method, endpoint, data, params, headers, retry_count + 1
                )
            else:
                handle_error(e)
                raise DrChronoAPIError(f"Network error: {str(e)}")
    
    # Convenience methods for HTTP operations
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """GET request"""
        return await self.make_request("GET", endpoint, params=params)
    
    async def post(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """POST request"""
        return await self.make_request("POST", endpoint, data=data)
    
    async def put(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """PUT request"""
        return await self.make_request("PUT", endpoint, data=data)
    
    async def patch(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """PATCH request"""
        return await self.make_request("PATCH", endpoint, data=data)
    
    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """DELETE request"""
        return await self.make_request("DELETE", endpoint)


class WebhookVerifier:
    """Utility for verifying DrChrono webhook signatures"""
    
    def __init__(self, secret_token: str):
        self.secret_token = secret_token
    
    def verify_signature(self, payload: str, signature: str) -> bool:
        """Verify webhook signature"""
        expected_signature = hmac.new(
            self.secret_token.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures securely
        return hmac.compare_digest(signature, expected_signature)
    
    def generate_verification_response(self, msg: str) -> str:
        """Generate verification response for webhook setup"""
        return hmac.new(
            self.secret_token.encode('utf-8'),
            msg.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()


def clean_phi_from_logs(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove or mask PHI from data for logging purposes"""
    sensitive_fields = {
        'social_security_number', 'ssn', 'date_of_birth', 'dob',
        'phone', 'email', 'address', 'emergency_contact',
        'first_name', 'last_name', 'middle_name', 'patient_photo'
    }
    
    def mask_sensitive_data(obj):
        if isinstance(obj, dict):
            return {
                key: "***MASKED***" if key.lower() in sensitive_fields or 'password' in key.lower()
                else mask_sensitive_data(value)
                for key, value in obj.items()
            }
        elif isinstance(obj, list):
            return [mask_sensitive_data(item) for item in obj]
        else:
            return obj
    
    return mask_sensitive_data(data)


# DrChrono API endpoint mappings and their levels
DRCHRONO_ENDPOINTS = {
    # Level 1 Endpoints
    "level_1": {
        "/api/allergies": "Patient allergy information",
        "/api/appointments": "Appointment scheduling and management",
        "/api/appointment_profiles": "Appointment profile templates",
        "/api/appointment_templates": "Appointment scheduling templates",
        "/api/billing_profiles": "Billing profile configurations",
        "/api/care_plans": "Patient care plan management",
        "/api/clinical_note_templates": "Clinical note templates",
        "/api/comm_logs": "Communication logs",
        "/api/consent_forms": "Patient consent forms",
        "/api/custom_appointment_fields": "Custom appointment field definitions",
        "/api/custom_demographics": "Custom demographic fields",
        "/api/custom_vitals": "Custom vital sign definitions",
        "/api/doctors": "Healthcare provider information",
        "/api/documents": "Document management",
        "/api/iframe_integration": "iFrame integration settings",
        "/api/implantable_devices": "Implantable device tracking",
        "/api/inventory_categories": "Inventory category management",
        "/api/inventory_vaccines": "Vaccine inventory management",
        "/api/medications": "Medication management",
        "/api/offices": "Medical office information",
        "/api/patients": "Patient demographic and basic information",
        "/api/patients/:id/ccda": "Patient CCDA document generation",
        "/api/patients/:id/qrda1": "Patient QRDA1 report generation",
        "/api/patients/:id/onpatient_access": "Patient portal access management",
        "/api/patient_communications": "Patient communication tracking",
        "/api/patient_flag_types": "Patient flag type definitions",
        "/api/patient_interventions": "Patient intervention tracking",
        "/api/patient_physical_exams": "Physical examination data",
        "/api/patient_risk_assessments": "Patient risk assessment data",
        "/api/patients_summary": "Patient summary information",
        "/api/problems": "Patient problem list management",
        "/api/reminder_profiles": "Appointment reminder profiles",
        "/api/telehealth_appointments": "Telehealth appointment management",
        "/api/users": "System user management",
        "/api/user_groups": "User group management",
        "/o/authorize": "OAuth authorization endpoint",
        "/o/revoke_token": "Token revocation endpoint",
        "/o/token": "Token management endpoint"
    },
    
    # Level 2 Endpoints
    "level_2": {
        "/api/amendments": "Medical record amendments",
        "/api/claim_billing_notes": "Insurance claim billing notes",
        "/api/clinical_notes": "Clinical documentation",
        "/api/clinical_note_field_types": "Clinical note field definitions",
        "/api/clinical_note_field_values": "Clinical note field values",
        "/api/custom_insurance_plan_names": "Custom insurance plan names",
        "/api/eligibility_checks": "Insurance eligibility verification",
        "/api/eobs": "Explanation of Benefits processing",
        "/api/fee_schedules": "Fee schedule management",
        "/api/insurances": "Patient insurance information",
        "/api/lab_documents": "Laboratory document management",
        "/api/lab_orders": "Laboratory order management",
        "/api/lab_orders_summary": "Laboratory order summaries",
        "/api/lab_tests": "Laboratory test definitions",
        "/api/lab_results": "Laboratory result management",
        "/api/line_items": "Billing line item management",
        "/api/medications/:id/append_to_pharmacy_note": "Pharmacy note management",
        "/api/messages": "Secure messaging system",
        "/api/offices/:id/add_exam_room": "Exam room management",
        "/api/pateint_lab_results": "Patient-specific lab results",
        "/api/patient_messages": "Patient messaging",
        "/api/patient_payments": "Patient payment processing",
        "/api/patient_payment_log": "Payment transaction logs",
        "/api/patient_vaccine_records": "Patient vaccination records",
        "/api/prescription_messages": "Prescription-related messaging",
        "/api/procedures": "Medical procedure management",
        "/api/sublabs": "Subcontracted laboratory management",
        "/api/tasks": "Clinical task management",
        "/api/task_categories": "Task category definitions",
        "/api/task_notes": "Task-related notes",
        "/api/task_templates": "Task template management",
        "/api/task_statuses": "Task status tracking",
        "/api/transactions": "Financial transaction management"
    }
}


def get_endpoint_info(endpoint: str) -> Dict[str, Any]:
    """Get information about a DrChrono API endpoint"""
    for level, endpoints in DRCHRONO_ENDPOINTS.items():
        if endpoint in endpoints:
            return {
                "level": level,
                "description": endpoints[endpoint],
                "is_level_2": level == "level_2"
            }
    
    return {
        "level": "unknown",
        "description": "Unknown endpoint",
        "is_level_2": False
    }