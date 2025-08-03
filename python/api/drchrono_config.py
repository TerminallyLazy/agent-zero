from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.clinical_api import ClinicalInboxAPI
from initialize import initialize_agent


class DrchronoConfig(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        base_url = input.get('base_url', 'https://app.drchrono.com/api')
        access_token = input.get('access_token', '')
        refresh_token = input.get('refresh_token', '')
        client_id = input.get('client_id', '')
        client_secret = input.get('client_secret', '')
        
        if not access_token:
            return {
                "success": False, 
                "message": "Access token is required"
            }
        
        try:
            # Initialize Clinical API
            config = initialize_agent()
            clinical_api = ClinicalInboxAPI(config)
            
            # Set DrChrono configuration
            clinical_api.set_drchrono_config({
                'base_url': base_url,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'client_id': client_id,
                'client_secret': client_secret
            })
            
            return {
                "success": True,
                "message": "DrChrono configuration updated successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to configure DrChrono: {str(e)}"
            }