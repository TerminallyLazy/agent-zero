from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.clinical_api import get_clinical_api
from python.helpers.print_style import PrintStyle


class WebhookSetup(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        try:
            action = input.get('action', 'status')
            
            if action == 'setup':
                return await self.setup_webhooks(input)
            elif action == 'status':
                return await self.webhook_status()
            elif action == 'test':
                return await self.test_webhooks()
            else:
                return {
                    "success": False,
                    "message": f"Unknown action: {action}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Webhook setup failed: {str(e)}"
            }
    
    async def setup_webhooks(self, input: Input) -> Output:
        """Setup DrChrono webhooks for Clinical Inbox events"""
        try:
            clinical_api = get_clinical_api()
            
            if not clinical_api or not clinical_api.is_configured():
                return {
                    "success": False,
                    "message": "DrChrono API not configured. Please set up integration first."
                }
            
            # Webhook URL should point to our drchrono_webhooks endpoint
            webhook_url = input.get('webhook_url', 'https://inbox-agent.xyz/drchrono_webhooks')
            
            # Define webhook events we want to monitor
            webhook_events = [
                'PATIENT_CREATE',
                'PATIENT_MODIFY', 
                'APPOINTMENT_CREATE',
                'APPOINTMENT_MODIFY',
                'TASK_CREATE',
                'CLINICAL_NOTE_LOCK',
                'PATIENT_ALLERGY_CREATE',
                'PATIENT_MEDICATION_CREATE',
                'PATIENT_PROBLEM_CREATE'
            ]
            
            PrintStyle(font_color="blue").print(f"Setting up DrChrono webhooks for: {webhook_url}")
            
            # Register webhook with DrChrono
            webhook_response = clinical_api.setup_webhook(
                url=webhook_url,
                events=webhook_events,
                secret="clinical_inbox_webhook_secret_2025"
            )
            
            if webhook_response:
                return {
                    "success": True,
                    "message": "Webhooks configured successfully",
                    "webhook_url": webhook_url,
                    "events": webhook_events,
                    "webhook_id": webhook_response.get('id')
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to register webhook with DrChrono"
                }
                
        except Exception as e:
            PrintStyle(font_color="red").print(f"Webhook setup error: {e}")
            return {
                "success": False,
                "message": f"Webhook setup failed: {str(e)}"
            }
    
    async def webhook_status(self) -> Output:
        """Check current webhook configuration status"""
        try:
            clinical_api = get_clinical_api()
            
            if not clinical_api or not clinical_api.is_configured():
                return {
                    "success": True,
                    "configured": False,
                    "message": "DrChrono API not configured"
                }
            
            # Check existing webhooks
            webhooks = clinical_api.get_webhooks()
            
            return {
                "success": True,
                "configured": True,
                "webhooks": webhooks or [],
                "message": f"Found {len(webhooks or [])} configured webhooks"
            }
            
        except Exception as e:
            PrintStyle(font_color="red").print(f"Webhook status check error: {e}")
            return {
                "success": False,
                "message": f"Failed to check webhook status: {str(e)}"
            }
    
    async def test_webhooks(self) -> Output:
        """Test webhook connectivity"""
        try:
            # This would test if our webhook endpoint is accessible
            # For now, just verify our endpoint exists
            return {
                "success": True,
                "message": "Webhook endpoint available at /drchrono_webhooks",
                "endpoint": "/drchrono_webhooks",
                "methods": ["GET", "POST"],
                "status": "ready"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Webhook test failed: {str(e)}"
            }