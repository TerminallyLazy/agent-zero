from typing import Dict, Any
from flask import Request
import requests
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.print_style import PrintStyle


class DrchronoOauth(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        code = input.get('code', '')
        client_id = input.get('client_id', '')
        client_secret = input.get('client_secret', '')
        redirect_uri = input.get('redirect_uri', '')
        
        if not code:
            return {
                "success": False, 
                "message": "Authorization code is required"
            }
        
        if not client_id or not client_secret:
            return {
                "success": False, 
                "message": "Client credentials are required"
            }
        
        try:
            # Exchange authorization code for access token
            token_url = "https://drchrono.com/o/token/"
            
            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': redirect_uri,
                'client_id': client_id,
                'client_secret': client_secret
            }
            
            response = requests.post(
                token_url,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                token_data = response.json()
                
                PrintStyle(font_color="green").print("DrChrono OAuth token exchange successful")
                
                return {
                    "success": True,
                    "access_token": token_data.get('access_token'),
                    "refresh_token": token_data.get('refresh_token'),
                    "expires_in": token_data.get('expires_in'),
                    "token_type": token_data.get('token_type', 'Bearer')
                }
            else:
                error_msg = f"Token exchange failed: {response.status_code} - {response.text}"
                PrintStyle(font_color="red").print(error_msg)
                return {
                    "success": False,
                    "message": error_msg
                }
                
        except Exception as e:
            error_msg = f"OAuth token exchange error: {str(e)}"
            PrintStyle(font_color="red").print(error_msg)
            return {
                "success": False,
                "message": error_msg
            }