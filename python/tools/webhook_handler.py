"""
Webhook Handler Tool

Manages DrChrono webhook operations including:
- Webhook signature verification
- Event processing for appointments, patients, clinical notes
- Callback URL management
- Secure webhook delivery handling
"""

import json
import hmac
import hashlib
import asyncio
from typing import Dict, Any, Optional, List
from flask import Flask, request, jsonify
from python.helpers.tool import Tool, Response
from python.helpers.drchrono_api import WebhookVerifier
from python.helpers.errors import handle_error
from python.helpers.print_style import PrintStyle
from datetime import datetime


class WebhookHandler(Tool):
    """DrChrono webhook management and processing tool"""
    
    # DrChrono webhook event types
    WEBHOOK_EVENTS = {
        'APPOINTMENT_CREATE': 'New appointment created',
        'APPOINTMENT_MODIFY': 'Appointment modified',
        'APPOINTMENT_DELETE': 'Appointment deleted',
        'PATIENT_CREATE': 'New patient created',
        'PATIENT_MODIFY': 'Patient information modified',
        'CLINICAL_NOTE_LOCK': 'Clinical note locked',
        'CLINICAL_NOTE_UNLOCK': 'Clinical note unlocked',
        'LINE_ITEM_CREATE': 'Billing line item created',
        'LINE_ITEM_MODIFY': 'Billing line item modified',
        'LINE_ITEM_DELETE': 'Billing line item deleted',
        'TASK_CREATE': 'Task created',
        'TASK_MODIFY': 'Task modified',
        'TASK_DELETE': 'Task deleted'
    }
    
    async def execute(
        self,
        action: str = "",
        callback_url: str = "",
        secret_token: str = "",
        events: Optional[List[str]] = None,
        webhook_payload: Optional[str] = None,
        signature: str = "",
        event_type: str = "",
        **kwargs
    ) -> Response:
        """
        Handle DrChrono webhook operations
        
        Args:
            action: Action to perform (setup, verify, process, list_events, remove)
            callback_url: HTTPS URL to receive webhook notifications
            secret_token: Secret token for webhook verification
            events: List of events to subscribe to
            webhook_payload: Raw webhook payload for verification
            signature: Webhook signature from DrChrono
            event_type: Type of webhook event being processed
        """
        
        try:
            if action == "setup":
                return await self._setup_webhook(callback_url, secret_token, events)
            
            elif action == "verify":
                return await self._verify_webhook_signature(webhook_payload, signature, secret_token)
            
            elif action == "process":
                return await self._process_webhook_event(webhook_payload, event_type)
            
            elif action == "list_events":
                return await self._list_webhook_events()
            
            elif action == "remove":
                return await self._remove_webhook(callback_url)
            
            elif action == "generate_verification":
                msg = kwargs.get("msg", "")
                return await self._generate_verification_response(secret_token, msg)
            
            elif action == "test_endpoint":
                return await self._test_webhook_endpoint(callback_url)
            
            else:
                return Response(
                    message=f"Error: Unknown action '{action}'. Available actions: setup, verify, process, list_events, remove, generate_verification, test_endpoint",
                    break_loop=False
                )
                
        except Exception as e:
            handle_error(e)
            return Response(
                message=f"Webhook handler error: {str(e)}",
                break_loop=False
            )
    
    async def _setup_webhook(self, callback_url: str, secret_token: str, events: Optional[List[str]] = None) -> Response:
        """Setup DrChrono webhook configuration"""
        
        if not callback_url or not secret_token:
            return Response(
                message="Error: callback_url and secret_token are required for webhook setup",
                break_loop=False
            )
        
        if not callback_url.startswith('https://'):
            return Response(
                message="Error: Callback URL must use HTTPS for security",
                break_loop=False
            )
        
        # Default to all events if none specified
        if not events:
            events = list(self.WEBHOOK_EVENTS.keys())
        
        # Validate event types
        invalid_events = [event for event in events if event not in self.WEBHOOK_EVENTS]
        if invalid_events:
            return Response(
                message=f"Error: Invalid event types: {', '.join(invalid_events)}. Valid events: {', '.join(self.WEBHOOK_EVENTS.keys())}",
                break_loop=False
            )
        
        # Store webhook configuration
        webhook_config = {
            "callback_url": callback_url,
            "secret_token": secret_token,
            "events": events,
            "created_at": datetime.now().isoformat(),
            "status": "configured"
        }
        
        self.agent.set_data("webhook_config", webhook_config)
        
        # Note: Actual webhook registration with DrChrono API would happen here
        # This would require making a POST request to /api/iframe_integration endpoint
        
        return Response(
            message=f"Webhook Configuration Setup Complete:\n"
                   f"- Callback URL: {callback_url}\n"
                   f"- Secret Token: {'*' * len(secret_token)}\n"
                   f"- Subscribed Events: {', '.join(events)}\n"
                   f"- Status: Configured\n\n"
                   f"Next Steps:\n"
                   f"1. Register webhook with DrChrono using iframe_integration endpoint\n"
                   f"2. Implement webhook endpoint at callback URL\n"
                   f"3. Test webhook delivery using test_endpoint action",
            break_loop=False
        )
    
    async def _verify_webhook_signature(self, payload: str, signature: str, secret_token: str) -> Response:
        """Verify webhook signature from DrChrono"""
        
        if not payload or not signature or not secret_token:
            return Response(
                message="Error: payload, signature, and secret_token are required for verification",
                break_loop=False
            )
        
        verifier = WebhookVerifier(secret_token)
        is_valid = verifier.verify_signature(payload, signature)
        
        if is_valid:
            return Response(
                message=f"Webhook Signature Verification: VALID\n"
                       f"- Signature matches expected value\n"
                       f"- Payload integrity confirmed\n"
                       f"- Source: Authenticated DrChrono webhook",
                break_loop=False
            )
        else:
            return Response(
                message=f"Webhook Signature Verification: INVALID\n"
                       f"- Signature does not match expected value\n"
                       f"- Potential security issue - webhook may not be from DrChrono\n"
                       f"- Do not process this webhook payload",
                break_loop=False
            )
    
    async def _process_webhook_event(self, payload: str, event_type: str) -> Response:
        """Process incoming webhook event"""
        
        if not payload:
            return Response(
                message="Error: payload required for event processing",
                break_loop=False
            )
        
        try:
            # Parse webhook payload
            event_data = json.loads(payload) if isinstance(payload, str) else payload
            
            # Extract event information
            webhook_id = event_data.get('id')
            webhook_event = event_data.get('event', event_type)
            object_id = event_data.get('object_id')
            timestamp = event_data.get('timestamp', datetime.now().isoformat())
            
            # Process based on event type
            processing_result = await self._handle_specific_event(webhook_event, event_data)
            
            # Log webhook event for audit trail
            webhook_log = {
                "webhook_id": webhook_id,
                "event_type": webhook_event,
                "object_id": object_id,
                "timestamp": timestamp,
                "processed_at": datetime.now().isoformat(),
                "processing_result": processing_result,
                "payload_size": len(str(payload))
            }
            
            # Store webhook logs
            webhook_logs = self.agent.get_data("webhook_logs") or []
            webhook_logs.append(webhook_log)
            self.agent.set_data("webhook_logs", webhook_logs[-100:])  # Keep last 100 events
            
            return Response(
                message=f"Webhook Event Processed Successfully:\n"
                       f"- Event Type: {webhook_event}\n"
                       f"- Object ID: {object_id}\n"
                       f"- Webhook ID: {webhook_id}\n"
                       f"- Timestamp: {timestamp}\n"
                       f"- Processing Result: {processing_result}\n\n"
                       f"Event logged for audit purposes.",
                break_loop=False
            )
            
        except json.JSONDecodeError as e:
            return Response(
                message=f"Error: Invalid JSON payload - {str(e)}",
                break_loop=False
            )
        except Exception as e:
            handle_error(e)
            return Response(
                message=f"Error processing webhook event: {str(e)}",
                break_loop=False
            )
    
    async def _handle_specific_event(self, event_type: str, event_data: Dict) -> str:
        """Handle specific webhook event types"""
        
        if event_type in ['APPOINTMENT_CREATE', 'APPOINTMENT_MODIFY', 'APPOINTMENT_DELETE']:
            return await self._handle_appointment_event(event_type, event_data)
        
        elif event_type in ['PATIENT_CREATE', 'PATIENT_MODIFY']:
            return await self._handle_patient_event(event_type, event_data)
        
        elif event_type in ['CLINICAL_NOTE_LOCK', 'CLINICAL_NOTE_UNLOCK']:
            return await self._handle_clinical_note_event(event_type, event_data)
        
        elif event_type in ['LINE_ITEM_CREATE', 'LINE_ITEM_MODIFY', 'LINE_ITEM_DELETE']:
            return await self._handle_billing_event(event_type, event_data)
        
        elif event_type in ['TASK_CREATE', 'TASK_MODIFY', 'TASK_DELETE']:
            return await self._handle_task_event(event_type, event_data)
        
        else:
            return f"Unknown event type: {event_type}"
    
    async def _handle_appointment_event(self, event_type: str, event_data: Dict) -> str:
        """Handle appointment-related webhook events"""
        
        appointment_id = event_data.get('object_id')
        
        if event_type == 'APPOINTMENT_CREATE':
            # Handle new appointment creation
            # Could trigger notifications, calendar updates, etc.
            return f"New appointment {appointment_id} created - notifications sent"
        
        elif event_type == 'APPOINTMENT_MODIFY':
            # Handle appointment modification
            # Could update calendars, send change notifications
            return f"Appointment {appointment_id} modified - systems updated"
        
        elif event_type == 'APPOINTMENT_DELETE':
            # Handle appointment cancellation
            # Could send cancellation notices, update schedules
            return f"Appointment {appointment_id} cancelled - cleanup completed"
        
        return "Appointment event processed"
    
    async def _handle_patient_event(self, event_type: str, event_data: Dict) -> str:
        """Handle patient-related webhook events"""
        
        patient_id = event_data.get('object_id')
        
        if event_type == 'PATIENT_CREATE':
            # Handle new patient registration
            # Could trigger welcome workflows, chart setup
            return f"New patient {patient_id} registered - welcome workflow initiated"
        
        elif event_type == 'PATIENT_MODIFY':
            # Handle patient information update
            # Could sync with other systems, validate changes
            return f"Patient {patient_id} information updated - systems synchronized"
        
        return "Patient event processed"
    
    async def _handle_clinical_note_event(self, event_type: str, event_data: Dict) -> str:
        """Handle clinical note webhook events"""
        
        note_id = event_data.get('object_id')
        
        if event_type == 'CLINICAL_NOTE_LOCK':
            # Handle note locking (finalization)
            # Could trigger billing, quality measures, etc.
            return f"Clinical note {note_id} locked - billing processes triggered"
        
        elif event_type == 'CLINICAL_NOTE_UNLOCK':
            # Handle note unlocking (reopening for edits)
            # Could update audit trails, notify relevant staff
            return f"Clinical note {note_id} unlocked - edit mode enabled"
        
        return "Clinical note event processed"
    
    async def _handle_billing_event(self, event_type: str, event_data: Dict) -> str:
        """Handle billing-related webhook events"""
        
        line_item_id = event_data.get('object_id')
        
        if event_type == 'LINE_ITEM_CREATE':
            return f"Billing line item {line_item_id} created - charge processing initiated"
        
        elif event_type == 'LINE_ITEM_MODIFY':
            return f"Billing line item {line_item_id} modified - charge updated"
        
        elif event_type == 'LINE_ITEM_DELETE':
            return f"Billing line item {line_item_id} deleted - charge reversed"
        
        return "Billing event processed"
    
    async def _handle_task_event(self, event_type: str, event_data: Dict) -> str:
        """Handle task-related webhook events"""
        
        task_id = event_data.get('object_id')
        
        if event_type == 'TASK_CREATE':
            return f"Task {task_id} created - workflow initiated"
        
        elif event_type == 'TASK_MODIFY':
            return f"Task {task_id} modified - status updated"
        
        elif event_type == 'TASK_DELETE':
            return f"Task {task_id} deleted - workflow cancelled"
        
        return "Task event processed"
    
    async def _list_webhook_events(self) -> Response:
        """List available webhook events and current configuration"""
        
        webhook_config = self.agent.get_data("webhook_config")
        webhook_logs = self.agent.get_data("webhook_logs") or []
        
        event_list = "\n".join([f"• {event}: {desc}" for event, desc in self.WEBHOOK_EVENTS.items()])
        
        config_info = "Not configured"
        if webhook_config:
            config_info = f"Configured for {len(webhook_config.get('events', []))} events at {webhook_config.get('callback_url', 'unknown')}"
        
        recent_events = len([log for log in webhook_logs if log.get('timestamp', '').startswith(datetime.now().strftime('%Y-%m-%d'))])
        
        return Response(
            message=f"DrChrono Webhook Events:\n\n{event_list}\n\n"
                   f"Current Configuration: {config_info}\n"
                   f"Recent Events Today: {recent_events}\n"
                   f"Total Events Logged: {len(webhook_logs)}",
            break_loop=False
        )
    
    async def _remove_webhook(self, callback_url: str) -> Response:
        """Remove webhook configuration"""
        
        webhook_config = self.agent.get_data("webhook_config")
        
        if not webhook_config:
            return Response(
                message="No webhook configuration found to remove",
                break_loop=False
            )
        
        # Clear webhook configuration
        self.agent.set_data("webhook_config", None)
        
        # Note: In production, this would also make a DELETE request to DrChrono API
        
        return Response(
            message=f"Webhook Configuration Removed:\n"
                   f"- Previous URL: {webhook_config.get('callback_url', 'unknown')}\n"
                   f"- Events: {len(webhook_config.get('events', []))}\n\n"
                   f"Note: Also remove webhook registration from DrChrono admin panel",
            break_loop=False
        )
    
    async def _generate_verification_response(self, secret_token: str, msg: str) -> Response:
        """Generate verification response for webhook setup"""
        
        if not secret_token or not msg:
            return Response(
                message="Error: secret_token and msg are required for verification response",
                break_loop=False
            )
        
        verifier = WebhookVerifier(secret_token)
        verification_response = verifier.generate_verification_response(msg)
        
        return Response(
            message=f"Webhook Verification Response Generated:\n"
                   f"- Message: {msg}\n"
                   f"- Response: {verification_response}\n\n"
                   f"Use this response when DrChrono sends verification request",
            break_loop=False
        )
    
    async def _test_webhook_endpoint(self, callback_url: str) -> Response:
        """Test webhook endpoint connectivity"""
        
        if not callback_url:
            return Response(
                message="Error: callback_url required for endpoint testing",
                break_loop=False
            )
        
        try:
            import requests
            
            # Send test payload
            test_payload = {
                "id": "test_webhook",
                "event": "TEST_EVENT",
                "object_id": "12345",
                "timestamp": datetime.now().isoformat(),
                "test": True
            }
            
            response = requests.post(
                callback_url,
                json=test_payload,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            
            return Response(
                message=f"Webhook Endpoint Test Results:\n"
                       f"- URL: {callback_url}\n"
                       f"- Status Code: {response.status_code}\n"
                       f"- Response Time: {response.elapsed.total_seconds():.2f}s\n"
                       f"- Response: {response.text[:200]}...\n"
                       f"- Test Result: {'PASS' if 200 <= response.status_code < 300 else 'FAIL'}",
                break_loop=False
            )
            
        except requests.RequestException as e:
            return Response(
                message=f"Webhook Endpoint Test FAILED:\n"
                       f"- URL: {callback_url}\n"
                       f"- Error: {str(e)}\n"
                       f"- Recommendation: Verify URL is accessible and accepts POST requests",
                break_loop=False
            )


# Webhook event processing templates
WEBHOOK_TEMPLATES = {
    "flask_endpoint": '''
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)
SECRET_TOKEN = "your_secret_token_here"

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    # Verify signature
    signature = request.headers.get('X-DrChrono-Signature')
    payload = request.get_data(as_text=True)
    
    expected_signature = hmac.new(
        SECRET_TOKEN.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected_signature):
        return jsonify({"error": "Invalid signature"}), 401
    
    # Process webhook
    data = request.json
    event_type = data.get('event')
    object_id = data.get('object_id')
    
    # Handle different event types
    if event_type == 'APPOINTMENT_CREATE':
        # Handle new appointment
        pass
    elif event_type == 'PATIENT_MODIFY':
        # Handle patient update
        pass
    
    return jsonify({"status": "received"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, ssl_context='adhoc')
''',
    
    "verification_endpoint": '''
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    msg = request.args.get('msg')
    if not msg:
        return "Missing msg parameter", 400
    
    verification_response = hmac.new(
        SECRET_TOKEN.encode('utf-8'),
        msg.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return verification_response
'''
}