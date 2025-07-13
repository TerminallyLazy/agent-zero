"""
DrChrono API Tool

Comprehensive DrChrono API integration tool providing:
- Complete endpoint coverage (Level 1 & 2)
- OAuth2 authentication management
- HIPAA-compliant operations
- Rate limiting and error handling
- Clinical workflow automation
"""

import json
import asyncio
from typing import Dict, Any, Optional, List
from python.helpers.tool import Tool, Response
from python.helpers.drchrono_api import (
    DrChronoClient, DrChronoConfig, TokenInfo, DrChronoAPIError,
    clean_phi_from_logs, get_endpoint_info, DRCHRONO_ENDPOINTS
)
from python.helpers.errors import handle_error
from python.helpers.print_style import PrintStyle
from datetime import datetime, timedelta


class DrChronoAPI(Tool):
    """DrChrono API tool for comprehensive EHR operations"""
    
    async def execute(
        self,
        endpoint: str = "",
        method: str = "GET",
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        operation: str = "",
        patient_id: Optional[str] = None,
        appointment_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        **kwargs
    ) -> Response:
        """
        Execute DrChrono API operations
        
        Args:
            endpoint: API endpoint (e.g., '/api/patients')
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            data: Request payload for POST/PUT/PATCH requests
            params: Query parameters
            operation: High-level operation name for common tasks
            patient_id: Patient ID for patient-specific operations
            appointment_id: Appointment ID for appointment operations
            doctor_id: Doctor ID for provider-specific operations
        """
        
        try:
            # Get configuration from agent context or environment
            config = await self._get_drchrono_config()
            
            # Load token information
            token_info = await self._load_token_info()
            if not token_info:
                return Response(
                    message="Error: DrChrono authentication required. Please authenticate first using oauth_manager tool.",
                    break_loop=False
                )
            
            # Handle high-level operations
            if operation:
                return await self._handle_operation(
                    config, token_info, operation, 
                    patient_id, appointment_id, doctor_id, data, params
                )
            
            # Handle direct endpoint calls
            if not endpoint:
                return Response(
                    message="Error: Either 'endpoint' or 'operation' parameter is required.",
                    break_loop=False
                )
            
            # Execute API request
            async with DrChronoClient(config) as client:
                client.set_token_info(token_info)
                
                # Get endpoint information
                endpoint_info = get_endpoint_info(endpoint)
                
                PrintStyle(font_color="#1B4F72").print(
                    f"Making {method} request to {endpoint} (Level {endpoint_info['level']})"
                )
                
                result = await client.make_request(
                    method=method,
                    endpoint=endpoint,
                    data=data,
                    params=params
                )
                
                # Clean PHI from logs
                logged_result = clean_phi_from_logs(result)
                
                return Response(
                    message=f"DrChrono API {method} {endpoint} completed successfully:\n{json.dumps(logged_result, indent=2)}",
                    break_loop=False
                )
                
        except DrChronoAPIError as e:
            error_msg = f"DrChrono API Error: {str(e)}"
            if e.status_code:
                error_msg += f" (Status: {e.status_code})"
            if e.response_data:
                error_msg += f"\nResponse: {json.dumps(e.response_data, indent=2)}"
            
            handle_error(e)
            return Response(message=error_msg, break_loop=False)
            
        except Exception as e:
            handle_error(e)
            return Response(
                message=f"Unexpected error: {str(e)}",
                break_loop=False
            )
    
    async def _get_drchrono_config(self) -> DrChronoConfig:
        """Get DrChrono configuration from agent context"""
        # Try to get from agent context/memory first
        try:
            config_data = self.agent.get_data("drchrono_config")
            if config_data:
                return DrChronoConfig(**config_data)
        except:
            pass
        
        # Default configuration - should be set via configuration tool
        return DrChronoConfig(
            client_id="",  # Should be set via environment or config
            client_secret="",  # Should be set via environment or config
            redirect_uri="http://localhost:8080/callback"
        )
    
    async def _load_token_info(self) -> Optional[TokenInfo]:
        """Load token information from agent memory"""
        try:
            token_data = self.agent.get_data("drchrono_tokens")
            if token_data:
                return TokenInfo(
                    access_token=token_data["access_token"],
                    refresh_token=token_data["refresh_token"],
                    expires_at=datetime.fromisoformat(token_data["expires_at"]),
                    token_type=token_data.get("token_type", "Bearer"),
                    scope=token_data.get("scope", "")
                )
        except Exception as e:
            handle_error(e)
        
        return None
    
    async def _handle_operation(
        self,
        config: DrChronoConfig,
        token_info: TokenInfo,
        operation: str,
        patient_id: Optional[str] = None,
        appointment_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Response:
        """Handle high-level DrChrono operations"""
        
        async with DrChronoClient(config) as client:
            client.set_token_info(token_info)
            
            try:
                if operation == "list_patients":
                    result = await self._list_patients(client, params)
                
                elif operation == "get_patient":
                    if not patient_id:
                        return Response(message="Error: patient_id required for get_patient operation", break_loop=False)
                    result = await self._get_patient(client, patient_id)
                
                elif operation == "create_patient":
                    if not data:
                        return Response(message="Error: patient data required for create_patient operation", break_loop=False)
                    result = await self._create_patient(client, data)
                
                elif operation == "update_patient":
                    if not patient_id or not data:
                        return Response(message="Error: patient_id and data required for update_patient operation", break_loop=False)
                    result = await self._update_patient(client, patient_id, data)
                
                elif operation == "list_appointments":
                    result = await self._list_appointments(client, params)
                
                elif operation == "get_appointment":
                    if not appointment_id:
                        return Response(message="Error: appointment_id required for get_appointment operation", break_loop=False)
                    result = await self._get_appointment(client, appointment_id)
                
                elif operation == "create_appointment":
                    if not data:
                        return Response(message="Error: appointment data required for create_appointment operation", break_loop=False)
                    result = await self._create_appointment(client, data)
                
                elif operation == "update_appointment":
                    if not appointment_id or not data:
                        return Response(message="Error: appointment_id and data required for update_appointment operation", break_loop=False)
                    result = await self._update_appointment(client, appointment_id, data)
                
                elif operation == "list_clinical_notes":
                    result = await self._list_clinical_notes(client, params)
                
                elif operation == "get_clinical_note":
                    note_id = kwargs.get("note_id")
                    if not note_id:
                        return Response(message="Error: note_id required for get_clinical_note operation", break_loop=False)
                    result = await self._get_clinical_note(client, note_id)
                
                elif operation == "list_doctors":
                    result = await self._list_doctors(client, params)
                
                elif operation == "get_doctor":
                    if not doctor_id:
                        return Response(message="Error: doctor_id required for get_doctor operation", break_loop=False)
                    result = await self._get_doctor(client, doctor_id)
                
                elif operation == "search_patients":
                    search_term = kwargs.get("search_term", "")
                    if not search_term:
                        return Response(message="Error: search_term required for search_patients operation", break_loop=False)
                    result = await self._search_patients(client, search_term)
                
                elif operation == "get_patient_summary":
                    if not patient_id:
                        return Response(message="Error: patient_id required for get_patient_summary operation", break_loop=False)
                    result = await self._get_patient_summary(client, patient_id)
                
                else:
                    return Response(
                        message=f"Error: Unknown operation '{operation}'. Available operations: list_patients, get_patient, create_patient, update_patient, list_appointments, get_appointment, create_appointment, update_appointment, list_clinical_notes, get_clinical_note, list_doctors, get_doctor, search_patients, get_patient_summary",
                        break_loop=False
                    )
                
                # Clean PHI from logs
                logged_result = clean_phi_from_logs(result)
                
                return Response(
                    message=f"DrChrono operation '{operation}' completed successfully:\n{json.dumps(logged_result, indent=2)}",
                    break_loop=False
                )
                
            except Exception as e:
                handle_error(e)
                return Response(
                    message=f"Error executing operation '{operation}': {str(e)}",
                    break_loop=False
                )
    
    # Patient Operations
    async def _list_patients(self, client: DrChronoClient, params: Optional[Dict] = None) -> Dict:
        """List patients with optional filtering"""
        query_params = params or {}
        return await client.get("/api/patients", params=query_params)
    
    async def _get_patient(self, client: DrChronoClient, patient_id: str) -> Dict:
        """Get specific patient by ID"""
        return await client.get(f"/api/patients/{patient_id}")
    
    async def _create_patient(self, client: DrChronoClient, patient_data: Dict) -> Dict:
        """Create new patient"""
        return await client.post("/api/patients", data=patient_data)
    
    async def _update_patient(self, client: DrChronoClient, patient_id: str, patient_data: Dict) -> Dict:
        """Update existing patient"""
        return await client.patch(f"/api/patients/{patient_id}", data=patient_data)
    
    async def _search_patients(self, client: DrChronoClient, search_term: str) -> Dict:
        """Search patients by name, phone, email, etc."""
        return await client.get("/api/patients", params={"search": search_term})
    
    async def _get_patient_summary(self, client: DrChronoClient, patient_id: str) -> Dict:
        """Get patient summary information"""
        return await client.get(f"/api/patients_summary/{patient_id}")
    
    # Appointment Operations
    async def _list_appointments(self, client: DrChronoClient, params: Optional[Dict] = None) -> Dict:
        """List appointments with optional filtering"""
        query_params = params or {}
        return await client.get("/api/appointments", params=query_params)
    
    async def _get_appointment(self, client: DrChronoClient, appointment_id: str) -> Dict:
        """Get specific appointment by ID"""
        return await client.get(f"/api/appointments/{appointment_id}")
    
    async def _create_appointment(self, client: DrChronoClient, appointment_data: Dict) -> Dict:
        """Create new appointment"""
        return await client.post("/api/appointments", data=appointment_data)
    
    async def _update_appointment(self, client: DrChronoClient, appointment_id: str, appointment_data: Dict) -> Dict:
        """Update existing appointment"""
        return await client.patch(f"/api/appointments/{appointment_id}", data=appointment_data)
    
    # Clinical Notes Operations
    async def _list_clinical_notes(self, client: DrChronoClient, params: Optional[Dict] = None) -> Dict:
        """List clinical notes with optional filtering"""
        query_params = params or {}
        return await client.get("/api/clinical_notes", params=query_params)
    
    async def _get_clinical_note(self, client: DrChronoClient, note_id: str) -> Dict:
        """Get specific clinical note by ID"""
        return await client.get(f"/api/clinical_notes/{note_id}")
    
    # Provider Operations
    async def _list_doctors(self, client: DrChronoClient, params: Optional[Dict] = None) -> Dict:
        """List doctors/providers"""
        query_params = params or {}
        return await client.get("/api/doctors", params=query_params)
    
    async def _get_doctor(self, client: DrChronoClient, doctor_id: str) -> Dict:
        """Get specific doctor by ID"""
        return await client.get(f"/api/doctors/{doctor_id}")


# Available operations for easy reference
AVAILABLE_OPERATIONS = {
    "Patient Management": [
        "list_patients",
        "get_patient", 
        "create_patient",
        "update_patient",
        "search_patients",
        "get_patient_summary"
    ],
    "Appointment Management": [
        "list_appointments",
        "get_appointment",
        "create_appointment", 
        "update_appointment"
    ],
    "Clinical Documentation": [
        "list_clinical_notes",
        "get_clinical_note"
    ],
    "Provider Management": [
        "list_doctors",
        "get_doctor"
    ]
}