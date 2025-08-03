import hashlib
import hmac
import json
from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.print_style import PrintStyle
from python.helpers.clinical_api import get_clinical_api


class DrchronoWebhooks(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False  # Webhooks come from DrChrono, not authenticated users
    
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST", "GET"]  # GET for verification, POST for webhooks
    
    async def process(self, input: Input, request: Request) -> Output:
        if request.method == 'GET':
            return await self.handle_verification(input, request)
        else:
            return await self.handle_webhook(input, request)
    
    async def handle_verification(self, input: Input, request: Request) -> Output:
        """Handle webhook verification from DrChrono"""
        try:
            # Get verification message from query params
            msg = request.args.get('msg')
            if not msg:
                return {"error": "Missing msg parameter"}, 400
            
            # Get webhook secret from DrChrono configuration
            webhook_secret = "1e0535a6bcffac57c9c666a33bd27746e5ee1892ab5f80c265038a9521f155a8"
            
            # Generate HMAC-SHA256 hash
            secret_token = hmac.new(
                webhook_secret.encode(),
                msg.encode(),
                hashlib.sha256
            ).hexdigest()
            
            PrintStyle(font_color="green").print(f"Webhook verification requested, responding with token")
            
            return {
                "secret_token": secret_token
            }
            
        except Exception as e:
            PrintStyle(font_color="red").print(f"Webhook verification failed: {e}")
            return {"error": str(e)}, 500
    
    async def handle_webhook(self, input: Input, request: Request) -> Output:
        """Handle incoming webhook from DrChrono"""
        try:
            # Get headers
            event_type = request.headers.get('X-drchrono-event')
            signature = request.headers.get('X-drchrono-signature')
            delivery_id = request.headers.get('X-drchrono-delivery')
            
            if not event_type:
                return {"error": "Missing X-drchrono-event header"}, 400
            
            # Handle PING
            if event_type == 'PING':
                PrintStyle(font_color="cyan").print("Received DrChrono webhook PING")
                return {"status": "pong"}
            
            # Verify signature for security
            webhook_secret = "1e0535a6bcffac57c9c666a33bd27746e5ee1892ab5f80c265038a9521f155a8"
            if signature and not self.verify_signature(request.data, signature, webhook_secret):
                PrintStyle(font_color="red").print(f"Invalid webhook signature from DrChrono")
                return {"error": "Invalid signature"}, 401
            
            # Get webhook payload
            payload = input
            receiver = payload.get('receiver', {})
            obj = payload.get('object', {})
            
            PrintStyle(font_color="blue").print(f"Received DrChrono webhook: {event_type}")
            
            # Process different webhook events
            result = await self.process_webhook_event(event_type, obj, delivery_id)
            
            return {"status": "processed", "event": event_type, "delivery_id": delivery_id}
            
        except Exception as e:
            PrintStyle(font_color="red").print(f"Webhook processing failed: {e}")
            return {"error": str(e)}, 500
    
    def verify_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify webhook signature"""
        try:
            expected_signature = hmac.new(
                secret.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(signature, expected_signature)
        except:
            return False
    
    async def process_webhook_event(self, event_type: str, obj: Dict, delivery_id: str) -> Dict[str, Any]:
        """Process specific webhook events"""
        clinical_api = get_clinical_api()
        
        # Log the event for audit trail
        await clinical_api.log_audit_event(
            event_type="webhook_received",
            category="integration",
            action=event_type,
            description=f"Received DrChrono webhook: {event_type}",
            details={
                "delivery_id": delivery_id,
                "object_id": obj.get('id'),
                "object_type": obj.get('__class__', 'unknown')
            }
        )
        
        # Process specific event types
        if event_type == 'PATIENT_CREATE':
            return await self.handle_patient_create(obj)
        elif event_type == 'PATIENT_MODIFY':
            return await self.handle_patient_modify(obj)
        elif event_type == 'APPOINTMENT_CREATE':
            return await self.handle_appointment_create(obj)
        elif event_type == 'APPOINTMENT_MODIFY':
            return await self.handle_appointment_modify(obj)
        elif event_type == 'TASK_CREATE':
            return await self.handle_task_create(obj)
        elif event_type == 'CLINICAL_NOTE_LOCK':
            return await self.handle_clinical_note_lock(obj)
        elif event_type in ['PATIENT_ALLERGY_CREATE', 'PATIENT_MEDICATION_CREATE', 'PATIENT_PROBLEM_CREATE']:
            return await self.handle_patient_data_update(event_type, obj)
        else:
            PrintStyle(font_color="yellow").print(f"Unhandled webhook event: {event_type}")
            return {"status": "unhandled", "event_type": event_type}
    
    async def handle_patient_create(self, patient: Dict) -> Dict[str, Any]:
        """Handle new patient creation"""
        PrintStyle(font_color="green").print(f"New patient created: {patient.get('first_name')} {patient.get('last_name')}")
        
        # Could trigger:
        # - Welcome message automation
        # - Onboarding workflow
        # - Profile setup reminders
        
        return {"action": "patient_welcomed"}
    
    async def handle_patient_modify(self, patient: Dict) -> Dict[str, Any]:
        """Handle patient information updates"""
        PrintStyle(font_color="blue").print(f"Patient updated: {patient.get('id')}")
        
        # Could trigger:
        # - Cache invalidation
        # - Profile sync
        # - Change notifications
        
        return {"action": "patient_synced"}
    
    async def handle_appointment_create(self, appointment: Dict) -> Dict[str, Any]:
        """Handle new appointment scheduling"""
        patient_id = appointment.get('patient')
        appointment_time = appointment.get('scheduled_time')
        
        PrintStyle(font_color="green").print(f"New appointment created for patient {patient_id} at {appointment_time}")
        
        # Could trigger:
        # - Confirmation messages
        # - Reminder scheduling
        # - Calendar updates
        # - Preparation workflows
        
        return {"action": "appointment_processed"}
    
    async def handle_appointment_modify(self, appointment: Dict) -> Dict[str, Any]:
        """Handle appointment changes"""
        PrintStyle(font_color="blue").print(f"Appointment modified: {appointment.get('id')}")
        
        # Could trigger:
        # - Change notifications
        # - Reschedule confirmations
        # - Calendar sync
        
        return {"action": "appointment_updated"}
    
    async def handle_task_create(self, task: Dict) -> Dict[str, Any]:
        """Handle new task creation"""
        PrintStyle(font_color="cyan").print(f"New task created: {task.get('description', 'Unknown')}")
        
        # Could trigger:
        # - Task assignment notifications
        # - Workflow automation
        # - Priority-based routing
        
        return {"action": "task_routed"}
    
    async def handle_clinical_note_lock(self, note: Dict) -> Dict[str, Any]:
        """Handle clinical note finalization"""
        PrintStyle(font_color="magenta").print(f"Clinical note locked: {note.get('id')}")
        
        # Could trigger:
        # - Billing automation
        # - Follow-up scheduling
        # - Documentation compliance checks
        
        return {"action": "note_processed"}
    
    async def handle_patient_data_update(self, event_type: str, data: Dict) -> Dict[str, Any]:
        """Handle patient medical data updates (allergies, medications, problems)"""
        patient_id = data.get('patient')
        PrintStyle(font_color="orange").print(f"Patient medical data updated: {event_type} for patient {patient_id}")
        
        # Could trigger:
        # - Clinical decision support alerts
        # - Drug interaction checks
        # - Care plan updates
        # - Provider notifications
        
        return {"action": "medical_data_processed"}